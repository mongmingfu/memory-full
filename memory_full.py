# ══════════════════════════════════════════════════════════════════════
# memory_full 板块地图（纯导航注释，不参与运行）
# ══════════════════════════════════════════════════════════════════════
#
# 【01】文件头 · 元信息 · 导入        文件最前 ~ APP_NAME 前
#        shebang / docstring / 全部 import
#
# 【02】枚举与业务常量                 APP_NAME ~ now_iso 前
#        ROLE_* / MEM_TYPE_* / MEM_STATUS_* / VIS_* / KN_* / BELIEF_*
#        RANK_W_* 打分常量 / 容量上限 / 阈值 / 词表
#
# 【03】工具函数层                     now_iso ~ LLMConfig 前
#        now_iso / _tokenize / _idf / _relevance / _similarity / _clamp
#        / _as_list / _bounded_str / _get_logger / setup_logging
#        / _rel_band / _local_ip
#
# 【04】配置层                         LLMConfig ~ Database 前
#        LLMConfig / MemoryConfig / Config
#        _load_config_file / _apply_section / load_config / hot_reload_config
#        + SQLite 相关常量
#
# 【05】数据库 + 建档上下文             Database ~ CharacterManager 前
#        Database（SQLite 封装、事务）
#        CreationContext（建档裁决上下文）
#
# 【06】角色管理                       CharacterManager ~ CardManager 前
#        CRUD / resolve_or_reject（建档裁决）/ get_user / auto_detect_active
#
# 【07】卡管理                         CardManager ~ EventManager 前
#        卡 CRUD / list_characters / card_of_character
#
# 【08】事件 + 可见性                   EventManager ~ MemoryManager 前
#        EventManager / VisibilityManager
#
# 【09】记忆管理（核心）                MemoryManager ~ KnowledgeManager 前
#        CRUD / 检索打分 / IDF / decay / wake_dormant / consolidate
#        / reinforce / 容量控制
#
# 【10】知识 + 信念                     KnowledgeManager ~ AssociationManager 前
#        KnowledgeManager / BeliefManager
#
# 【11】关联 + 关系 + 状态              AssociationManager ~ CommitmentManager 前
#        AssociationManager / RelationshipManager / StateManager
#
# 【12】承诺 + 秘密                     CommitmentManager ~ LLMClient 前
#        CommitmentManager / SecretManager
#
# 【13】LLM 客户端                       LLMClient ~ ExtractionResult 前
#        上游 OpenAI 兼容调用
#
# 【14】抽取器                         ExtractionResult ~ TavoImporter 前
#        ExtractionResult / MemoryExtractor
#        窗口构造 / PROMPT_SYSTEM / LLM 抽取 / C2 候选 / 规则回退
#        _is_card_rule_text / _is_scaffold_text / _is_ooc_meta_text
#
# 【15】Tavo 导入                       TavoImporter ~ ContextBuilder 前
#        JSONL 导入
#
# 【16】上下文组装                     ContextBuilder ~ MemoryEngine 前
#        build()：五层组装 / B2 本轮在场 / 场景状态（0c）/ 剧情时间（0d）
#        / RELAY_MEMORY_INTRO 模板 / Token 预算分配
#
# 【17】总装引擎                       MemoryEngine ~ WebServer 前
#        中继管线 / 识别 / 归属 / 拆条 / 延迟一拍 / 场景抽取+仲裁
#        / 剧情时间解析 / 建档守卫 / 落库 / build_context
#
# 【18】Web 服务 + HTTP handler         WebServer ~ _chat_between_user_name 前
#        WebServer 类 / _make_handler / do_GET / do_POST
#        / 全部 /api/* / 中继路由 / UI HTML / 闸门
#
# 【19】中继工具函数                   _chat_between_user_name ~ _force_utf8_stdout 前
#        _actor_names_from_text / extract_real_user_text / _relay_* 系列
#        / _dump_extract_debug / _is_ooc_meta_text 等
#
# 【20】CLI 层                         _force_utf8_stdout ~ 文件末
#        _table / _kv / _open_engine / 全部 cmd_* 子命令 / build_cli / cli()
#
# ══════════════════════════════════════════════════════════════════════
# 用法（grep 之前先看这里）：
#   · 改配置逻辑       → 【04】
#   · 改记忆衰减/检索   → 【09】
#   · 改抽取 prompt     → 【14】
#   · 改上下文注入      → 【16】
#   · 改中继管线/识别   → 【17】
#   · 改 UI / 路由      → 【18】
#   · 加新 CLI 命令     → 【20】
#
# 注意：行号会随着每次补丁位移。本图只做"定位起点"用，
#       真正定位时用 grep -n "^class XXX" 或 grep -n "def YYY"。
# ══════════════════════════════════════════════════════════════════════
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 memory_full.py — Tavo / SillyTavern 通用多角色长期记忆引擎（单文件）
================================================================================

 本文件严格实现 SPEC.md（同目录）。核心真理：

     事件发生了 ≠ 所有人知道了 ≠ 所有人记住了
              ≠ 所有人相信了 ≠ 所有人对它采取相同态度

 四层分离：
     Events（客观事件）
        ↓
     event_visibility（谁知道/怀疑/听说）   memories（谁记得什么）
        ↓
     knowledge（谁知道哪些非事件事实）
        ↓
     beliefs（谁怎么理解）
        ↓
     relationships（关系数值）
        ↓
     Stance（当前行为倾向，不落库）

 依赖：仅标准库（pyyaml 可选，用于读 config.yaml）。

-------------------------------------------------------------------------------
 [本文件分 5 批写入，当前进度：批 1]
   批 1：文件头 / 常量 / 工具函数 / 配置 / SQL Schema / Database /
         CharacterManager / EventManager / VisibilityManager
   批 2：MemoryManager / KnowledgeManager / BeliefManager / AssociationManager
   批 3：RelationshipManager / StateManager / CommitmentManager / SecretManager
   批 4：LLMClient / ExtractionResult / PROMPT_SYSTEM / MemoryExtractor /
         TavoImporter / ContextBuilder
   批 5：MemoryEngine / WebServer / CLI / main / 使用文档
-------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

# ---------- 可选依赖：pyyaml（缺失时只能读 JSON 配置）----------
try:  # pragma: no cover
    import yaml  # type: ignore
    _HAS_YAML = True
except Exception:  # pragma: no cover
    yaml = None  # type: ignore
    _HAS_YAML = False


# ==============================================================================
# 全局常量
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【02】枚举与业务常量
# ══════════════════════════════════════════════════════════════════════

APP_NAME = "memory_full"
APP_VERSION = "2.0.0"
SCHEMA_VERSION = 2
DEFAULT_ENCODING = "utf-8"

# ---------- characters.role_type ----------
ROLE_USER = "user"
ROLE_MAIN = "main_character"
ROLE_NPC = "npc"
ROLE_SYSTEM = "system"
ROLE_UNKNOWN = "unknown"
VALID_ROLE_TYPES: Tuple[str, ...] = (
    ROLE_USER, ROLE_MAIN, ROLE_NPC, ROLE_SYSTEM, ROLE_UNKNOWN,
)
# [全角色 main] 新建角色默认就是 main_character（用户要求：不再自动落 npc/unknown）
DEFAULT_ROLE_TYPE = ROLE_MAIN
#: 晋升顺序（越大越核心）
ROLE_TYPE_RANK: Dict[str, int] = {
    ROLE_UNKNOWN: 0, ROLE_SYSTEM: 1, ROLE_NPC: 2, ROLE_MAIN: 3, ROLE_USER: 4,
}

# ---------- event_visibility.state（没有 UNKNOWN！）----------
VIS_KNOWN = "KNOWN"
VIS_SUSPECTED = "SUSPECTED"
VIS_RUMORED = "RUMORED"
VALID_VISIBILITY_STATES: Tuple[str, ...] = (VIS_KNOWN, VIS_SUSPECTED, VIS_RUMORED)
VISIBILITY_RANK: Dict[str, int] = {VIS_RUMORED: 1, VIS_SUSPECTED: 2, VIS_KNOWN: 3}
#: 这两个状态必须携带非空 partial_content（强制校验 1 / 13）
VISIBILITY_NEEDS_PARTIAL: Tuple[str, ...] = (VIS_SUSPECTED, VIS_RUMORED)
#: 同级更新时允许被覆盖的字段（强制校验 13-b）
VISIBILITY_SAME_LEVEL_FIELDS: Tuple[str, ...] = (
    "partial_content", "confidence", "source", "source_message_ids", "updated_at",
)
#: 同级更新时禁止被改动的字段（强制校验 13-b）
VISIBILITY_LOCKED_FIELDS: Tuple[str, ...] = ("state", "present", "role_in_event")

# ---------- event_visibility.role_in_event ----------
ROLE_IN_EVENT_VALUES: Tuple[str, ...] = (
    "speaker", "actor", "victim", "witness", "nearby", "mentioned_only",
)
DEFAULT_ROLE_IN_EVENT: Optional[str] = None

# ---------- event_visibility.source ----------
SOURCE_FIRSTHAND = "firsthand"
SOURCE_INFERRED = "inferred"
SOURCE_WITNESSED_PARTIALLY = "witnessed_partially"
SOURCE_HEARD_FROM_PREFIX = "heard_from:"
#: 固定取值（heard_from:<name> 为前缀式开放取值，另行校验）
FIXED_VISIBILITY_SOURCES: Tuple[str, ...] = (
    SOURCE_FIRSTHAND, SOURCE_INFERRED, SOURCE_WITNESSED_PARTIALLY,
)
DEFAULT_VISIBILITY_SOURCE = SOURCE_FIRSTHAND
DEFAULT_VISIBILITY_CONFIDENCE = 0.7
#: source 字符串长度上限（heard_from:<name> 里 name 可能不短）
MAX_SOURCE_LEN = 128
#: source_message_ids JSON 数组的容量上限
MAX_SOURCE_MESSAGE_IDS = 200

# ---------- memories.memory_type ----------
MEM_TYPE_EPISODIC = "episodic"
MEM_TYPE_SEMANTIC = "semantic"
MEM_TYPE_RELATIONSHIP = "relationship"
MEM_TYPE_EMOTIONAL = "emotional"
MEM_TYPE_PROCEDURAL = "procedural"
MEM_TYPE_SECRET = "secret"
MEM_TYPE_COMMITMENT = "commitment"
MEM_TYPE_CONFLICT = "conflict"
MEM_TYPE_PREFERENCE = "preference"
MEM_TYPE_IDENTITY = "identity"
MEM_TYPE_WORLD_EVENT = "world_event"
VALID_MEMORY_TYPES: Tuple[str, ...] = (
    MEM_TYPE_EPISODIC, MEM_TYPE_SEMANTIC, MEM_TYPE_RELATIONSHIP,
    MEM_TYPE_EMOTIONAL, MEM_TYPE_PROCEDURAL, MEM_TYPE_SECRET,
    MEM_TYPE_COMMITMENT, MEM_TYPE_CONFLICT, MEM_TYPE_PREFERENCE,
    MEM_TYPE_IDENTITY, MEM_TYPE_WORLD_EVENT,
)
#: 事件型 memory：必须有 source_event_id（强制校验 5）
EVENT_BOUND_MEMORY_TYPES: Tuple[str, ...] = (
    MEM_TYPE_EPISODIC, MEM_TYPE_WORLD_EVENT, MEM_TYPE_CONFLICT,
    MEM_TYPE_COMMITMENT, MEM_TYPE_SECRET,
)
#: 非事件型 memory：允许没有 source_event_id
NON_EVENT_MEMORY_TYPES: Tuple[str, ...] = (
    MEM_TYPE_SEMANTIC, MEM_TYPE_RELATIONSHIP, MEM_TYPE_EMOTIONAL,
    MEM_TYPE_PROCEDURAL, MEM_TYPE_PREFERENCE, MEM_TYPE_IDENTITY,
)
DEFAULT_MEMORY_TYPE = MEM_TYPE_EPISODIC

# ---------- memories.source_type 来源枚举（V? 增量）----------
MEM_SOURCE_USER = "USER"                # 用户明确陈述
MEM_SOURCE_OBSERVATION = "OBSERVATION"  # 角色通过实际剧情观察到的
MEM_SOURCE_DIRECTIVE = "DIRECTIVE"      # 明确既成事实型元指令造成的
MEM_SOURCE_INFERENCE = "INFERENCE"      # 模型根据上下文推断
MEM_SOURCE_HEARSAY = "HEARSAY"          # 角色从其他角色处听到的
MEM_SOURCE_UNKNOWN = "UNKNOWN"          # 历史数据无法确定来源
#: 合法来源枚举（CLI / Web UI / API 校验用）
VALID_MEMORY_SOURCES = (
    MEM_SOURCE_USER, MEM_SOURCE_OBSERVATION, MEM_SOURCE_DIRECTIVE,
    MEM_SOURCE_INFERENCE, MEM_SOURCE_HEARSAY, MEM_SOURCE_UNKNOWN)


def _inherit_source_type(rows) -> str:
    """合并类写入的来源：源行 source_type 一致则继承，否则 UNKNOWN（不猜）。"""
    seen = set()
    for r in (rows or []):
        try:
            seen.add(str((r if isinstance(r, dict) else {})
                         .get("source_type") or MEM_SOURCE_UNKNOWN).strip().upper())
        except Exception:
            seen.add(MEM_SOURCE_UNKNOWN)
    return seen.pop() if len(seen) == 1 else MEM_SOURCE_UNKNOWN
VALID_MEMORY_SOURCE_TYPES: Tuple[str, ...] = (
    MEM_SOURCE_USER, MEM_SOURCE_OBSERVATION, MEM_SOURCE_DIRECTIVE,
    MEM_SOURCE_INFERENCE, MEM_SOURCE_HEARSAY, MEM_SOURCE_UNKNOWN,
)
DEFAULT_MEMORY_SOURCE_TYPE = MEM_SOURCE_UNKNOWN

# ---------- memories.status ----------
MEM_STATUS_ACTIVE = "active"
MEM_STATUS_REINFORCED = "reinforced"
MEM_STATUS_WEAKENED = "weakened"
MEM_STATUS_CONSOLIDATED = "consolidated"
MEM_STATUS_SUPERSEDED = "superseded"
MEM_STATUS_CONTRADICTED = "contradicted"
MEM_STATUS_ARCHIVED = "archived"
#: [V6 阶段B] 休眠：``recall_strength < MEM_DORMANT_THRESHOLD`` 时进入。
#: 检索默认**不加载**它；但用户提问命中它的关键词时会被「高相关唤醒」
#: 改回 ``active`` 并加回 0.2 强度（见 MemoryManager.retrieve）。
MEM_STATUS_DORMANT = "dormant"
VALID_MEMORY_STATUSES: Tuple[str, ...] = (
    MEM_STATUS_ACTIVE, MEM_STATUS_REINFORCED, MEM_STATUS_WEAKENED,
    MEM_STATUS_CONSOLIDATED, MEM_STATUS_SUPERSEDED, MEM_STATUS_CONTRADICTED,
    MEM_STATUS_ARCHIVED, MEM_STATUS_DORMANT,
)
#: consolidation 的候选状态
CONSOLIDATION_INPUT_STATUSES: Tuple[str, ...] = (
    MEM_STATUS_ACTIVE, MEM_STATUS_REINFORCED,
)

# ---------- memories.consolidated_mode ----------
CONSOLIDATED_MODE_RAW = "raw"
CONSOLIDATED_MODE_LLM = "llm"
VALID_CONSOLIDATED_MODES: Tuple[str, ...] = (
    CONSOLIDATED_MODE_RAW, CONSOLIDATED_MODE_LLM,
)

# ---------- knowledge.status ----------
KN_KNOWN = "KNOWN"
KN_UNKNOWN = "UNKNOWN"
KN_SUSPECTED = "SUSPECTED"
KN_RUMORED = "RUMORED"
KN_FORGOTTEN = "FORGOTTEN"
VALID_KNOWLEDGE_STATUSES: Tuple[str, ...] = (
    KN_KNOWN, KN_UNKNOWN, KN_SUSPECTED, KN_RUMORED, KN_FORGOTTEN,
)
DEFAULT_KNOWLEDGE_STATUS = KN_UNKNOWN

# ---------- beliefs ----------
BELIEF_FACT = "FACT"
BELIEF_BELIEF = "BELIEF"
BELIEF_ATTITUDE = "ATTITUDE"
BELIEF_SELF_BELIEF = "SELF_BELIEF"
BELIEF_JUDGMENT = "JUDGMENT"
VALID_BELIEF_KINDS: Tuple[str, ...] = (
    BELIEF_FACT, BELIEF_BELIEF, BELIEF_ATTITUDE, BELIEF_SELF_BELIEF,
    BELIEF_JUDGMENT,
)
#: LLM 只允许写这 4 种；FACT 只能由规则层产出（强制校验 2）
LLM_WRITABLE_BELIEF_KINDS: Tuple[str, ...] = (
    BELIEF_BELIEF, BELIEF_ATTITUDE, BELIEF_SELF_BELIEF, BELIEF_JUDGMENT,
)

BELIEF_SUBJECT_PERSON = "person"
BELIEF_SUBJECT_EVENT = "event"
BELIEF_SUBJECT_FACT = "fact"
BELIEF_SUBJECT_SELF = "self"
VALID_BELIEF_SUBJECT_KINDS: Tuple[str, ...] = (
    BELIEF_SUBJECT_PERSON, BELIEF_SUBJECT_EVENT, BELIEF_SUBJECT_FACT,
    BELIEF_SUBJECT_SELF,
)

GENERATED_BY_RULE = "rule"
GENERATED_BY_LLM = "llm"
VALID_BELIEF_GENERATORS: Tuple[str, ...] = (GENERATED_BY_RULE, GENERATED_BY_LLM)

BELIEF_STATUS_ACTIVE = "active"
BELIEF_STATUS_SUPERSEDED = "superseded"
BELIEF_STATUS_CONTRADICTED = "contradicted"
BELIEF_STATUS_ARCHIVED = "archived"
VALID_BELIEF_STATUSES: Tuple[str, ...] = (
    BELIEF_STATUS_ACTIVE, BELIEF_STATUS_SUPERSEDED,
    BELIEF_STATUS_CONTRADICTED, BELIEF_STATUS_ARCHIVED,
)
#: 单向流转：只有 active 能离开（强制校验 3）
BELIEF_LEAVABLE_STATUS = BELIEF_STATUS_ACTIVE
BELIEF_TARGET_STATUSES: Tuple[str, ...] = (
    BELIEF_STATUS_SUPERSEDED, BELIEF_STATUS_CONTRADICTED, BELIEF_STATUS_ARCHIVED,
)
DEFAULT_BELIEF_CONFIDENCE = 0.7

# ---------- commitments.status ----------
COMMITMENT_ACTIVE = "active"
COMMITMENT_FULFILLED = "fulfilled"
COMMITMENT_BROKEN = "broken"
COMMITMENT_EXPIRED = "expired"
COMMITMENT_UNKNOWN = "unknown"
VALID_COMMITMENT_STATUSES: Tuple[str, ...] = (
    COMMITMENT_ACTIVE, COMMITMENT_FULFILLED, COMMITMENT_BROKEN,
    COMMITMENT_EXPIRED, COMMITMENT_UNKNOWN,
)
DEFAULT_COMMITMENT_STATUS = COMMITMENT_ACTIVE
COMMITMENT_OPEN_STATUSES: Tuple[str, ...] = (COMMITMENT_ACTIVE, COMMITMENT_UNKNOWN)

# ---------- secrets.status ----------
SECRET_ACTIVE = "active"
SECRET_REVEALED = "revealed"
SECRET_OBSOLETE = "obsolete"
VALID_SECRET_STATUSES: Tuple[str, ...] = (
    SECRET_ACTIVE, SECRET_REVEALED, SECRET_OBSOLETE,
)
DEFAULT_SECRET_STATUS = SECRET_ACTIVE

# ---------- relationships 数值字段（全部 0.0~1.0）----------
REL_TRUST = "trust"
REL_AFFECTION = "affection"
REL_RESENTMENT = "resentment"
REL_FAMILIARITY = "familiarity"
REL_RESPECT = "respect"
REL_FEAR = "fear"
REL_DEPENDENCY = "dependency"
ALLOWED_REL_FIELDS: Tuple[str, ...] = (
    REL_TRUST, REL_AFFECTION, REL_RESENTMENT, REL_FAMILIARITY,
    REL_RESPECT, REL_FEAR, REL_DEPENDENCY,
)
#: 新建关系行时的初值（与 schema 的 DEFAULT 保持一致）
REL_DEFAULT_VALUES: Dict[str, float] = {
    REL_TRUST: 0.5, REL_AFFECTION: 0.5, REL_RESENTMENT: 0.0,
    REL_FAMILIARITY: 0.5, REL_RESPECT: 0.5, REL_FEAR: 0.0,
    REL_DEPENDENCY: 0.0,
}
REL_MIN = 0.0
REL_MAX = 1.0
#: 单次 delta 绝对值上限；超过即拒绝（强制校验 7）
REL_MAX_DELTA = 0.5
# ---------- [relations-1] 三档事件映射：tier -> delta 上限 ----------
REL_TIER_MAJOR_MIN = 0.4          # imp >= 0.4 起算 major
REL_TIER_IRREVERSIBLE_MIN = 0.6   # imp >= 0.6 起算 irreversible
REL_DELTA_CAP_DAILY = 0.05
REL_DELTA_CAP_MAJOR = 0.20
REL_DELTA_CAP_IRREVERSIBLE = 0.50
# ---------- [relations-2] 关系证据 anchor ----------
ANCHOR_FETCH_LIMIT = 6            # 多取几条，为 reason 去重留余量
ANCHOR_MAX_ITEMS = 3              # 最终最多输出 3 条
ANCHOR_REASON_MAX_LEN = 50        # 超过就按标点截首句
ANCHOR_MIN_LEN = 8                # 截不出 >= 8 字的合格句 -> 放弃

# ---------- [relations-5] 状态句滞后带（只影响注入措辞，不回写数值）----------
REL_BAND_BUFFER = 0.03            # 阈值 ± REL_BAND_BUFFER 内维持原档
REL_BAND_CACHE_MAX = 1000         # 档位缓存上限，超出丢最早的一条

# ---------- [relations-6] SLOW 维度上升打折 ----------
REL_SLOW_DIMENSIONS: frozenset = frozenset(
    {REL_TRUST, REL_RESPECT, REL_DEPENDENCY})
REL_SLOW_UP_DISCOUNT = 0.6        # 上升打 0.6 折；下跌原速

# ---------- [relations-7a] 怨恨（resentment）峰值 + 残留下限 ----------
REL_HATE_FIELD = REL_RESENTMENT   # 本项目的 "hate" 就是 resentment 字段
HATE_DEFAULT_FLOOR_RATIO = 0.15   # 残留下限 = hate_peak * ratio
REL_HATE_FLOOR_REASON = "怨恨残留下限（peak×ratio）"

# ---------- [relations-8] 强状态周期性重申 ----------
REL_AFFIRM_PERIOD_STRONG = 4      # hate>0.7 / dep>0.8 / trust>0.85
REL_AFFIRM_PERIOD_WEAK = 8        # hate>0.5
REL_AFFIRM_CACHE_MAX = 1000
REL_WATCH_DIMS: Tuple[Tuple[str, float, int], ...] = (
    (REL_RESENTMENT, 0.70, REL_AFFIRM_PERIOD_STRONG),
    (REL_DEPENDENCY, 0.80, REL_AFFIRM_PERIOD_STRONG),
    (REL_TRUST, 0.85, REL_AFFIRM_PERIOD_STRONG),
    (REL_RESENTMENT, 0.50, REL_AFFIRM_PERIOD_WEAK),
)

# ---------- [relations-9] 低置信度维度弱信号累积 ----------
REL_WEAK_SIGNAL_COUNT = 3
REL_WEAK_INIT_REASON = "弱信号累积初始化"
ANCHOR_SENTENCE_SEPS: Tuple[str, ...] = ("。", "！", "？", "；")

# ---------- [P0] 初始关系：从角色卡设定文本抽取 ----------
REL_INIT_HISTORY_REASON = "初始关系（从角色卡抽取）"
REL_INIT_PERSONA_MAX_LEN = 4000        # 卡文本送进 LLM 前的截断长度
REL_INIT_VALID_CONF: Tuple[str, ...] = ("high", "medium", "low", "unset")
#: 低置信度档位：这两档**不写入**关系值
REL_INIT_SKIP_CONF: Tuple[str, ...] = ("low", "unset")
#: LLM 返回的 JSON 键 -> relationships 列名（hate 对应 resentment）
REL_INIT_FIELD_MAP: Tuple[Tuple[str, str], ...] = (
    ("trust", REL_TRUST),
    ("affection", REL_AFFECTION),
    ("respect", REL_RESPECT),
    ("familiarity", REL_FAMILIARITY),
    ("dependency", REL_DEPENDENCY),
    ("hate", REL_RESENTMENT),
    ("fear", REL_FEAR),
)
REL_INIT_SYSTEM_PROMPT = """你是角色关系抽取器。阅读以下角色设定文本，为该角色对"用户"的初始关系，输出 7 个维度的值。

维度：trust 信任 / affection 好感 / respect 敬重 / familiarity 熟悉 / dependency 依赖 / hate 怨恨 / fear 畏惧

每个维度输出三字段：
- value: 0.0-1.0 浮点
- confidence: "high" | "medium" | "low" | "unset"
  * high: 文本明确写了（如"她是你妻子" -> familiarity/trust high）
  * medium: 从身份合理推断
  * low: 只能靠猜
  * unset: 完全没提这个维度
- evidence: 文本里支撑的句子（无则空字符串）

严格只输出 JSON，无多余文字：
{
  "trust":       {"value": 0.9, "confidence": "high", "evidence": "结婚八年"},
  "affection":   {"value": 0.88, "confidence": "high", "evidence": "..."},
  "respect":     {"value": null, "confidence": "unset", "evidence": ""},
  "familiarity": {"value": 0.9, "confidence": "high", "evidence": "..."},
  "dependency":  {"value": 0.7, "confidence": "medium", "evidence": "..."},
  "hate":        {"value": 0.02, "confidence": "high", "evidence": ""},
  "fear":        {"value": null, "confidence": "unset", "evidence": ""}
}

规则：
- 没提到且推不出来的维度，value 写 null，confidence 写 "unset"
- 绝不为填满字段而硬给 0.5
- 数值要具体，不要都给 0.5 或 0.7"""

# ---------- [元指令] 手动关系推进 ----------
META_CMD_MIN_CONFIDENCE = 0.8          # 低于此置信度按普通对话处理
META_CMD_PLACEHOLDER = "（玩家执行了一条指令）"
META_CMD_REASON_MAX_LEN = 50
#: target_level -> 绝对设定值
META_LEVEL_VALUES: Dict[str, float] = {
    "hate": 0.1, "cold": 0.3, "normal": 0.5, "trust": 0.7, "intimate": 0.9,
}
#: 指代"玩家本人"的写法（全部小写比较）
META_CMD_USER_ALIASES: Tuple[str, ...] = ("用户", "user", "玩家", "我")
#: LLM 给的 dimension 写法 -> relationships 列名（hate 对应 resentment）
META_DIM_SYNONYMS: Dict[str, str] = {
    "trust": REL_TRUST,
    "affection": REL_AFFECTION,
    "love": REL_AFFECTION,
    "respect": REL_RESPECT,
    "familiarity": REL_FAMILIARITY,
    "dependency": REL_DEPENDENCY,
    "hate": REL_RESENTMENT,
    "resentment": REL_RESENTMENT,
    "fear": REL_FEAR,
}
META_CMD_SYSTEM_PROMPT = """你是元指令识别器。玩家在角色扮演对话中，可能插入"给系统的指令"（不是对角色说的话），比如"一年后我们结婚了"、"我拿走了她的初夜"、"我们分手了"。

识别以下元指令：
- 关系变化：描述关系变好/变坏/身份变化
- 时间跳跃：明确的时间推进（如"一年后"）

输出 JSON：
{
  "is_meta": true/false,
  "confidence": 0.0-1.0,
  "changes": [
    {
      "from": "角色名或'用户'",
      "to": "角色名或'用户'",
      "dimension": "trust|affection|respect|familiarity|dependency|hate|fear",
      "target_level": "hate|cold|normal|trust|intimate",
      "reason": "简短原因（≤50字）"
    }
  ]
}

规则：
- 普通剧情对话 -> is_meta: false
- 明确描述关系变化或时间跳跃 -> true
- confidence < 0.8 -> 视为 false
- 一句话可对应多个维度变化
- "结婚" -> affection/trust/familiarity/dependency 全推 intimate
- "初夜" -> affection/familiarity/dependency 推 intimate
- "如胶似漆" -> affection/dependency 推 intimate
- "分手/离婚" -> trust/affection 推 hate，dependency 推 hate

【什么不是元指令 —— 必须返回 is_meta: false】

以下情况即使在文本上"看起来像元指令"，也一律不是元指令：

1. 提议 / 祈使 / 未发生
   - "我们结婚吧"（提议，还没发生）
   - "要不要在一起"（询问）
   - "我们分手吧"（提议分手）

2. 引述 / 嵌套对话
   - "某人对我说：'我们结婚吧'"
   - "他说'我讨厌你'"
   - 任何有明确"某人说'...'"结构的

3. 假设 / 虚拟 / 反事实
   - "如果当时没走，我们现在应该结婚了"
   - "要是他道歉，我就原谅他"
   - "假如我们分手"

4. 疑问 / 反问
   - "我们算不算在一起了？"
   - "你还爱我吗？"

5. 单纯描述情绪/状态，不涉及关系变化
   - "我好累"
   - "今天心情不错"

【判定优先级】
先判断"是不是元指令"（以上 5 类都 false），
再判断"元指令里要改什么"。

只有以下情况是元指令：
- 明确的时间跳跃（"一年后"、"三年过去了"）
- 明确的既成事实关系变化（"我们结婚了"、"我拿走了她的初夜"、"我们离婚了"）
- 玩家用括号类符号显式标记的段（(（ )）、【】、[]）

只输出 JSON，无多余文字。"""

# ---------- character_states 字段 ----------
#: 表达"角色自身当前状态"的字段
ALLOWED_STATE_FIELDS: Tuple[str, ...] = (
    "emotion", "mood", "anger", "fear", "stress",
    "relationship_state", "current_goal", "current_location",
    "physical_state", "mental_context", "unresolved_conflicts", "summary",
)
#: 兼容旧版字段：保留但不作为"对他人关系"的真相源（强制校验 11 / 原则 10）
STATE_COMPAT_FIELDS: Tuple[str, ...] = ("trust", "affection")
STATE_VALUE_MAX_LEN = 8000

# ---------- events.event_type ----------
EVENT_TYPE_WORLD = "world_event"
EVENT_TYPE_CONFLICT = "conflict"
EVENT_TYPE_COMMITMENT = "commitment"
EVENT_TYPE_SECRET = "secret"
EVENT_TYPE_DIALOGUE = "dialogue"
EVENT_TYPE_REVELATION = "revelation"
EVENT_TYPE_TRAVEL = "travel"
EVENT_TYPE_GIFT = "gift"
EVENT_TYPE_INJURY = "injury"
EVENT_TYPE_MEETING = "meeting"
EVENT_TYPE_OTHER = "other"
VALID_EVENT_TYPES: Tuple[str, ...] = (
    EVENT_TYPE_WORLD, EVENT_TYPE_CONFLICT, EVENT_TYPE_COMMITMENT,
    EVENT_TYPE_SECRET, EVENT_TYPE_DIALOGUE, EVENT_TYPE_REVELATION,
    EVENT_TYPE_TRAVEL, EVENT_TYPE_GIFT, EVENT_TYPE_INJURY,
    EVENT_TYPE_MEETING, EVENT_TYPE_OTHER,
)
DEFAULT_EVENT_TYPE = EVENT_TYPE_WORLD

# ---------- 抽取 / 压缩模式（CLI 的 --mode）----------
MODE_FAST = "fast"
MODE_NORMAL = "normal"
MODE_DEEP = "deep"
VALID_MODES: Tuple[str, ...] = (MODE_FAST, MODE_NORMAL, MODE_DEEP)
DEFAULT_MODE = MODE_NORMAL
#: 需要调用 LLM 的模式
LLM_MODES: Tuple[str, ...] = (MODE_NORMAL, MODE_DEEP)

# ---------- cards（V3 追加：卡片层）----------
CARD_SOURCE_TAVO = "tavo"
CARD_SOURCE_MANUAL = "manual"
CARD_SOURCE_IMPORT = "import"
CARD_SOURCE_LLM = "llm"
VALID_CARD_SOURCES: Tuple[str, ...] = (
    CARD_SOURCE_TAVO, CARD_SOURCE_MANUAL, CARD_SOURCE_IMPORT, CARD_SOURCE_LLM,
)
DEFAULT_CARD_SOURCE = CARD_SOURCE_TAVO
#: [V2.2 铁律] 兜底卡名：**角色必须有 card_id，严禁散装角色**。
#: 中继请求没给卡名（``_current_card`` 为空）时，新角色一律挂到这张卡下。
DEFAULT_CARD_NAME = "默认卡"

#: [V2.4 兜底防呆] **纯称呼**（亲属/关系称谓）——它们不是角色名。
#: 中继/抽取要**新建**角色时：先按真名 + 别名解析；解析不到、且名字落在这里，
#: 就**拒绝建档**并打 WARN（避免又造出「爸爸」「女儿」这种无意义空壳角色）。
#: 故意**不含**「主人 / 大人 / 小姐」——那些在角色扮演里可能就是正式角色。
KINSHIP_ADDRESS_WORDS: Tuple[str, ...] = (
    "爸爸", "爸", "父亲", "老爸", "爹", "爹地", "父上",
    "妈妈", "妈", "母亲", "老妈", "娘", "娘亲", "母上",
    "哥哥", "哥", "兄长", "弟弟", "弟", "弟弟君",
    "姐姐", "姐", "姊", "妹妹", "妹",
    "爷爷", "祖父", "奶奶", "祖母", "外公", "姥爷", "外婆", "姥姥",
    "叔叔", "叔父", "舅舅", "姑姑", "阿姨", "婶婶", "伯父", "伯母",
    "儿子", "女儿", "闺女", "孩子",
    "老公", "老婆", "丈夫", "妻子", "太太", "夫人",
    "孙子", "孙女",
)

#: V3 消息归属：content 开头的 "角色名：xxx" / "角色名: xxx"
MSG_OWNER_PREFIX_PATTERNS: Tuple[str, ...] = (
    r"^\s*[「『\"']?([^\s：:，,。.、！!？?\n]{1,32})[」』\"']?\s*[：:]\s*\S",
)

#: V3 LLM 兜底识别：各输入的截断长度
LLM_CARD_DETECT_SYSTEM_CHARS = 3000
LLM_CARD_DETECT_MSG_CHARS = 500
LLM_CARD_DETECT_MSG_COUNT = 3

#: V3 识别来源标签
DETECT_SOURCE_QUERY = "query"
DETECT_SOURCE_HEADER = "header"
DETECT_SOURCE_LOCAL_SCAN = "local_scan"
DETECT_SOURCE_LLM = "llm_fallback"
DETECT_SOURCE_DEFAULT = "default"
DETECT_SOURCE_RESOLVE_ACTIVE = "resolve_active"
DETECT_SOURCE_NONE = "none"

# ---------- 记忆衰减 ----------
MEM_BASE_DECAY_RATE = 0.01
#: 重要/情感强烈的记忆衰减更慢：effective_rate = base / (1 + importance·W1 + emotion·W2)
DECAY_IMPORTANCE_SLOWDOWN = 2.0
DECAY_EMOTION_SLOWDOWN = 1.0
MEM_RECALL_FLOOR = 0.02
MEM_RECALL_CEIL = 3.0
MEM_WEAKEN_THRESHOLD = 0.15
MEM_REINFORCE_DEFAULT = 0.25
#: 被压缩成摘要的原始记忆，强度乘以该系数（SPEC 明确规定 0.5）
CONSOLIDATED_SOURCE_FACTOR = 0.5
DEFAULT_IMPORTANCE = 0.5
DEFAULT_CONFIDENCE = 0.7
DEFAULT_EMOTIONAL_INTENSITY = 0.5
DEFAULT_RECALL_STRENGTH = 1.0
CONSOLIDATE_SUMMARY_MAX_LEN = 300

# ---------- 检索 ----------
RETRIEVE_DEFAULT_LIMIT = 20
RETRIEVE_MIN_SCORE = 0.02
RANK_W_RELEVANCE = 1.0
RANK_W_RECALL = 1.0
RANK_W_IMPORTANCE = 0.3
ASSOC_EXPAND_LIMIT = 5
ASSOC_EXPAND_DISCOUNT = 0.5

# ---------- 规则抽取 ----------
RULE_MIN_TEXT_LEN = 4
RULE_EVENT_MIN_TEXT_LEN = 12
RULE_SUMMARY_MAX_LEN = 200
#: 明确承诺（SPEC 给定正则语义）
COMMITMENT_PATTERNS: Tuple[str, ...] = (
    r"我(?:答应|保证|发誓|承诺|立誓)", r"我(?:一定|绝对)会", r"说好了",
    r"我(?:向你|对你)保证", r"不会(?:忘|辜负)", r"我发誓",
)
#: 明确秘密（SPEC 给定正则语义）
SECRET_PATTERNS: Tuple[str, ...] = (
    r"不要告诉", r"别告诉", r"不许说", r"保密", r"这是(?:个)?秘密",
    r"只有你知道", r"别说出去", r"不要外传", r"藏在心里",
)
#: 情绪词识别（爱/恨/怕/怒/喜）
EMOTION_WORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("喜", ("开心", "高兴", "快乐", "兴奋", "愉快", "幸福", "喜悦", "笑")),
    ("怒", ("愤怒", "生气", "恼火", "火大", "可恶", "恨", "怒")),
    ("哀", ("难过", "伤心", "悲伤", "失落", "绝望", "心痛", "哭")),
    ("惧", ("害怕", "恐惧", "慌张", "紧张", "不安", "颤抖", "怕")),
    ("爱", ("喜欢", "爱", "心动", "温柔", "眷恋", "想念", "思念")),
    ("惊", ("惊讶", "震惊", "意外", "没想到", "吃惊", "居然")),
)
EMOTION_INTENSITY_STEP = 0.2
#: 重要性粗估用的关键词（关键词 -> 加分）
IMPORTANCE_KEYWORDS: Tuple[Tuple[str, float], ...] = (
    ("记住", 0.3), ("别忘了", 0.3), ("别忘", 0.3), ("发誓", 0.3),
    ("永远", 0.25), ("约定", 0.25), ("承诺", 0.25), ("重要", 0.25),
    ("生日", 0.25), ("秘密", 0.25), ("一定", 0.2), ("名字", 0.2),
    ("我叫", 0.2), ("设定", 0.2), ("规则", 0.2), ("第一次", 0.2),
    ("喜欢", 0.15), ("讨厌", 0.15), ("我是", 0.15),
)

# ---------- 角色活跃度 / 晋升 ----------
ACTIVE_WINDOW_MESSAGES = 30
ACTIVE_WINDOW_HOURS = 72
MAIN_PROMOTE_MIN_MESSAGES = 20
MAIN_PROMOTE_MIN_DAYS = 1.0
NAME_MAX_LEN = 64
ALIAS_MAX_COUNT = 16
ALIAS_MAX_LEN = 64

# ---------- 事件链 ----------
MAX_CHAIN_EVENTS = 500

# ---------- 容量 ----------
MAX_EVENTS_PER_DB = 100000
MAX_MEMORIES_PER_CHARACTER = 5000
ENFORCE_CAPACITY = True

# ---------- LLM ----------
LLM_DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
LLM_DEFAULT_API_KEY = "local"
LLM_DEFAULT_MODEL = "local-model"
LLM_DEFAULT_TEMPERATURE = 0.2
LLM_DEFAULT_MAX_TOKENS = 1500
LLM_DEFAULT_TIMEOUT = 60.0
LLM_DEFAULT_RETRIES = 2
LLM_MAX_RESPONSE_BYTES = 4_000_000
#: 流式转发时上游 SSE 的总字节上限（防呆，超过即主动截断；批 8 追加）
LLM_MAX_STREAM_BYTES = 8 * 1024 * 1024
LLM_RETRY_BACKOFF_SEC = 0.6
LLM_USER_AGENT = f"{APP_NAME}/{APP_VERSION}"

# ---------- 服务 ----------
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8081

# ---------- 存储 ----------
DEFAULT_DB_PATH = "memory.db"
DEFAULT_CONFIG_NAMES: Tuple[str, ...] = ("config.yaml", "config.yml", "config.json")
SQLITE_TIMEOUT = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_JOURNAL_MODE = "WAL"

# ---------- 日志 ----------
LOG_DIR = "logs"
LOG_FILENAME = "memory_full.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_LEVEL = "INFO"

# ---------- JSON 列（读取时自动反序列化）----------
JSON_COLUMNS: Tuple[str, ...] = (
    "aliases", "profile", "static_profile", "traits",
    "source_message_ids", "tags", "consolidated_from", "revealed_to",
    "cover",
    # [V6 阶段D] 被合并掉的旧记忆 id 列表（JSON 数组，读出来就是 list）
    "merged_from",
)
EMPTY_JSON_ARRAY = "[]"
EMPTY_JSON_OBJECT = "{}"

# ---------- 噪声过滤（工具函数 _is_trivial 用）----------
TRIVIAL_PATTERNS: Tuple[str, ...] = (
    r"^[\s\W_]+$",
    r"^(嗯+|哦+|啊+|噢+|呃+|唔+|哈+|呵+|嘿+|诶+|唉+)[。！.!~]*$",
    r"^(好的?|是|对|嗯嗯|OK|ok|行|可以|收到|明白|了解|知道了?)[。！.!~]*$",
    r"^(哈哈+|嘿嘿+|嘻嘻+|呵呵+)[。！.!~]*$",
    r"^(然后|接着|所以|但是|而且|因为|就是)[，,]*$",
)
TRIVIAL_COMPILED: Tuple[re.Pattern, ...] = tuple(
    re.compile(p) for p in TRIVIAL_PATTERNS
)


# ==============================================================================
# 时区（全库时间统一使用北京时间）
# ==============================================================================
#: 生成与显示统一使用的时区：北京时间 UTC+8。
#: 显式固定偏移，**不跟随系统时区** —— 本机系统时区实测为美东（UTC-4），
#: 跟随系统只会继续写出非北京的时间串。
BEIJING_TZ = timezone(timedelta(hours=8), "CST")
#: 北京时间的 UTC 偏移秒数（供 ``logging`` 的时间转换器使用）。
BEIJING_UTC_OFFSET_SECONDS = 8 * 3600


# ==============================================================================
# 工具函数
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【03】工具函数层
# ══════════════════════════════════════════════════════════════════════

def now_iso() -> str:
    """当前时间，北京时间（UTC+8）ISO-8601 字符串（秒精度）。

    全库时间字段统一使用本函数，保证字符串可按字典序正确排序 ——
    新写入的行都带同一个 ``+08:00`` 偏移，因此字典序仍等于时间序。
    """
    return datetime.now(BEIJING_TZ).replace(microsecond=0).isoformat()


def now_ts() -> float:
    """当前 Unix 时间戳（秒，浮点）。用于记忆衰减计算。"""
    return time.time()


def _parse_iso(value: Any) -> Optional[datetime]:
    """宽松解析 ISO-8601 / 时间戳，失败返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    txt = str(value).strip()
    if not txt:
        return None
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _norm_iso(value: Any, default: Optional[str] = None) -> Optional[str]:
    """把任意时间表示归一化成 now_iso() 风格；解析失败返回 default。"""
    dt = _parse_iso(value)
    if dt is None:
        return default
    return dt.replace(microsecond=0).isoformat()


def _hours_since(value: Any, now: Optional[float] = None) -> float:
    """距给定时间已过多少小时（无法解析时返回 0）。"""
    dt = _parse_iso(value)
    if dt is None:
        return 0.0
    ref = datetime.fromtimestamp(
        float(now) if now is not None else time.time(), tz=timezone.utc)
    return max(0.0, (ref - dt).total_seconds() / 3600.0)


# 检索停用词：这类 token 几乎出现在每条记忆里，参与打分只会稀释真正的
# 实词命中——这正是"长文本仅因字多就更容易命中"的根因之一。
# 注意：分词器只产出「单字 + 相邻二元组」，所以长度 > 2 的词条永远不会
# 被匹配到（例如 "为什么"），保留仅为可读性与日后扩展。
STOP_WORDS = frozenset({
    "的", "了", "是", "我", "你", "在", "和", "就", "不", "人", "都",
    "一", "上", "也", "很", "到", "说", "要", "去", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "他", "她", "它", "们", "而", "及",
    "与", "等", "但", "或", "被", "把", "让", "给", "对", "从", "向",
    "于", "以", "为", "之", "其", "此", "该", "各", "每", "某", "哪",
    "谁", "什么", "怎么", "为什么", "如何", "是否", "可以", "能", "会",
    "应该", "必须", "需要", "可能",
})

#: 检索时的 query 同义词扩展表（同一概念的不同说法）。
#: 命中 query 里任一 key 就拼上对应的词，让「规矩」能带出「越界/边界」。
#: 手工维护，可增可删。
QUERY_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "规矩": ("越界", "边界", "底线", "分寸", "认主", "抱亲", "隔衣"),
    "承诺": ("答应", "保证", "发誓", "说好", "立誓", "守约"),
    "喜欢": ("爱", "心动", "在意", "好感", "眷恋", "思念"),
    "害怕": ("恐惧", "畏惧", "忌惮", "慌张"),
    "生气": ("愤怒", "恼火", "发火", "不快", "气愤"),
    "秘密": ("隐瞒", "瞒着", "藏着", "不说"),
    "关系": ("信任", "亲近", "疏远", "依赖"),
    "答应": ("承诺", "保证", "说好"),
    "爱": ("喜欢", "心动", "在意", "眷恋"),
    "信任": ("相信", "依赖", "托付"),
}

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_WS_RE = re.compile(r"\s+")


def _tokenize(text: str) -> List[str]:
    """中英混合分词（不依赖第三方库）。

    * 拉丁/数字串整体作为一个 token（小写归一）
    * 连续汉字：单字 + 相邻二元组，兼顾召回与精度
    """
    s = (text or "").strip().lower()
    if not s:
        return []
    tokens: List[str] = _WORD_RE.findall(s)
    for run in _CJK_RUN_RE.findall(s):
        tokens.extend(run)
        if len(run) > 1:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def _token_set(text: Any) -> set:
    """文本 -> token 集合。"""
    return set(_tokenize(str(text or "")))


def _token_jaccard(a: Any, b: Any) -> float:
    """两个 token 集合的 Jaccard 相似度，∈[0,1]。"""
    sa = a if isinstance(a, set) else _token_set(a)
    sb = b if isinstance(b, set) else _token_set(b)
    if not sa or not sb:
        return 0.0
    union = len(sa | sb)
    return (len(sa & sb) / union) if union else 0.0


IDF_MIN_CORPUS = 200    # 语料小于此规模时不启用 IDF（小库 idf 无统计意义）

DF_CACHE_MEM_LIMIT_MB = 30.0   # 所有 owner 的 df 总内存上限；超出退化为单份全局 df
DF_BUILD_CHUNK_ROWS = 500      # 每处理这么多行让出一次 GIL
DF_GLOBAL_OWNER = -1           # 「全局一份」模式的哨兵 key（owner id 恒为正）
DF_BYTES_PER_TOKEN = 108       # 实测：df 字典 ≈ 108 bytes / 唯一 token


def _gil_enabled() -> bool:
    """当前解释器是否启用 GIL（3.13 之前无此接口，恒视为启用）。"""
    fn = getattr(sys, "_is_gil_enabled", None)
    if fn is None:
        return True
    try:
        return bool(fn())
    except Exception:
        return True


#: free-threaded 构建才需要锁；标准 GIL 构建下为 None（单条属性赋值即原子）
_DF_PUBLISH_LOCK = None if _gil_enabled() else threading.Lock()


def _idf(token: str, df: Dict[str, int], n_docs: int) -> float:
    """BM25 常用形式的 IDF，恒正。"""
    d = int(df.get(token, 0))
    return math.log(1.0 + (n_docs - d + 0.5) / (d + 0.5))


def _df_stats(rows: Any) -> Tuple[int, Dict[str, int]]:
    """P1 供数：在给定候选集内统计 ``(N, {token: df})``。

    不建表、不动写路径；代价是 df 在一个有偏样本上估计（候选集是按
    recall_strength 取的前 N 条），N 小时噪声大，故由 IDF_MIN_CORPUS 兜住。
    """
    df: Dict[str, int] = {}
    n = 0
    for r in (rows or []):
        n += 1
        for t in _token_set(r.get("content")):
            df[t] = df.get(t, 0) + 1
    return n, df


def _expand_query(query: Any) -> str:
    """检索前把 query 拼上同义词，让「规矩」能带出「越界/边界」。

    不改 _relevance 内部 —— 扩展后的字符串按原样送进去。
    查不到同义词 / 空 query 就原样返回。
    """
    q = str(query or "").strip()
    if not q:
        return q
    syns: List[str] = []
    try:
        tokens = _token_set(q)
        for tok in tokens:
            for s in QUERY_SYNONYMS.get(tok, ()):
                if s not in syns and s not in q:
                    syns.append(s)
    except Exception:
        return q
    if not syns:
        return q
    return q + " " + " ".join(syns)


def _relevance(query: Any, content: Any, df_stats: Any = None) -> float:
    """查询相关度：命中 token 占查询 token 的比例，∈[0,1]。

    停用词（``STOP_WORDS``）不参与打分：它们遍布几乎所有记忆内容，
    保留在分母里只会稀释真正的实词命中，让"话多"的记忆白占便宜。
    查询过滤停用词后已无有效 token 时返回 0.0（旧行为返回 1.0，
    那会让所有候选拿到同一个满分，相关度项等于作废）。
    """
    q = _token_set(query) - STOP_WORDS
    if not q:
        return 0.0
    c = _token_set(content)
    if not c:
        return 0.0
    hit = q & c
    if not hit:
        return 0.0
    # [IDF] 语料统计不足时不启用，精确退化为均匀权重（等价老逻辑）
    if df_stats is not None:
        n_docs, df = df_stats
        if n_docs >= IDF_MIN_CORPUS:
            weights = {t: _idf(t, df, n_docs) for t in q}
            denom = sum(weights.values())
            if denom > 0.0:
                return sum(weights[t] for t in hit) / denom
    return len(hit) / len(q)


def _similarity(a: Any, b: Any) -> float:
    """字符级相似度（用于摘要/冲突的粗判），∈[0,1]。"""
    sa = _WS_RE.sub("", str(a or ""))
    sb = _WS_RE.sub("", str(b or ""))
    if not sa or not sb:
        return 0.0
    if sa == sb:
        return 1.0
    return SequenceMatcher(None, sa, sb).ratio()


def _is_trivial(text: str) -> bool:
    """判断文本是否为无信息量的噪声（语气词 / 纯标点 / 纯表情 / 客套应答）。

    注意：本函数**不**按长度判断，长度门限由调用方的 RULE_MIN_TEXT_LEN 负责。
    """
    t = (text or "").strip()
    if not t:
        return True
    for pat in TRIVIAL_COMPILED:
        if pat.match(t):
            return True
    return False


def _sha(text: Any, length: int = 16) -> str:
    """内容指纹：先做空白/大小写归一，再取 sha1 前 length 位十六进制。"""
    norm = _WS_RE.sub("", str(text if text is not None else "")).lower()
    digest = hashlib.sha1(norm.encode(DEFAULT_ENCODING, errors="replace")).hexdigest()
    return digest[:max(4, int(length))]


def _parse_json_safe(raw: Any, default: Any = None) -> Any:
    """容错 JSON 解析：剥掉 ``` 围栏、截取首个 [] 或 {} 块，失败返回 default。"""
    if raw is None:
        return default
    if isinstance(raw, (dict, list, int, float, bool)):
        return raw
    txt = str(raw).strip()
    if not txt:
        return default
    txt = re.sub(r"^\s*```(?:json|JSON)?\s*", "", txt)
    txt = re.sub(r"\s*```\s*$", "", txt).strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    for pat in (r"\[.*\]", r"\{.*\}"):
        m = re.search(pat, txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                continue
    return default


def _json_dumps(obj: Any) -> str:
    """序列化为 JSON 字符串（不转义非 ASCII，便于人工查看）。"""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return EMPTY_JSON_ARRAY if isinstance(obj, (list, tuple, set)) else EMPTY_JSON_OBJECT


def _as_list(value: Any) -> List[Any]:
    """把任意值宽松地规整成 list（用于 JSON 数组列）。"""
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        parsed = _parse_json_safe(value, None)
        if isinstance(parsed, list):
            return parsed
        s = value.strip()
        return [s] if s else []
    return [value]


def _as_dict(value: Any) -> Dict[str, Any]:
    """把任意值宽松地规整成 dict（用于 JSON 对象列）。"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = _parse_json_safe(value, None)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _clamp(value: Any, lo: float = 0.0, hi: float = 1.0,
           default: float = 0.0) -> float:
    """数值夹取；无法转 float 或为 NaN 时返回 default。"""
    try:
        f = float(value)
    except Exception:
        return float(default)
    if f != f:  # NaN
        return float(default)
    return max(float(lo), min(float(hi), f))


def _bounded_str(value: Any, max_len: int, default: str = "") -> str:
    """安全转字符串并截断。"""
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    return s[:int(max_len)]


def _to_int(value: Any) -> Optional[int]:
    """宽松转 int；失败或布尔值返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _beijing_converter(sec: Optional[float] = None) -> time.struct_time:
    """``logging`` 用：把时间戳换算成北京时间的 ``struct_time``。"""
    stamp = time.time() if sec is None else float(sec)
    return time.gmtime(stamp + BEIJING_UTC_OFFSET_SECONDS)


def _get_logger(suffix: str = "") -> logging.Logger:
    """取子 logger；即使没调用 setup_logging 也不会丢日志。"""
    name = f"{APP_NAME}.{suffix}" if suffix else APP_NAME
    return logging.getLogger(name)


def setup_logging(
    debug: bool = False,
    log_dir: str = LOG_DIR,
    log_file: str = LOG_FILENAME,
    level: Optional[str] = None,
) -> logging.Logger:
    """初始化日志。

    * 始终写入 ``<log_dir>/<log_file>``（默认 ``logs/memory_full.log``）
    * ``debug=True`` 时同时输出到 stderr
    * 任何目录/文件创建失败都只告警，不中断程序
    """
    lvl_name = (level or ("DEBUG" if debug else DEFAULT_LOG_LEVEL)).upper()
    lvl = getattr(logging, lvl_name, logging.INFO)

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(lvl)
    for h in list(logger.handlers):
        logger.removeHandler(h)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    #: 日志行首时间戳同样固定用北京时间（``logging`` 默认跟随系统时区）
    formatter.converter = _beijing_converter

    # ---- 文件handler（必选）----
    try:
        d = Path(log_dir)
        d.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(d / log_file, encoding=DEFAULT_ENCODING)
        fh.setFormatter(formatter)
        fh.setLevel(lvl)
        logger.addHandler(fh)
    except Exception as ex:  # pragma: no cover
        print(f"[memory_full] 日志文件创建失败，仅输出到 stderr：{ex}",
              file=sys.stderr)

    # ---- DEBUG 模式额外输出 stderr ----
    if debug or lvl <= logging.DEBUG:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(formatter)
        sh.setLevel(lvl)
        logger.addHandler(sh)

    logger.propagate = False
    return logger


def _local_ip() -> str:
    """尽力获取本机局域网 IP，失败退化为 127.0.0.1。"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except Exception:
        try:
            return str(socket.gethostbyname(socket.gethostname()))
        except Exception:
            return "127.0.0.1"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


# ==============================================================================
# 配置 dataclass
# ==============================================================================

# ==============================================================================
# [V6 追加] 记忆生命周期（多维） + 安全聚合合并 —— 全局常量
# ==============================================================================
# ---- 记忆分层 tier：1=身份/核心关系/不可逆事件 … 4=当前情绪/动作/场景 ----
TIER_CORE = 1
TIER_IMPORTANT = 2
TIER_NORMAL = 3
TIER_TRANSIENT = 4
VALID_TIERS: Tuple[int, ...] = (TIER_CORE, TIER_IMPORTANT, TIER_NORMAL,
                                TIER_TRANSIENT)
DEFAULT_TIER = TIER_NORMAL
#: 这几个 memory_type 天然属于「身份 / 核心关系」-> tier 1
TIER1_MEMORY_TYPES: Tuple[str, ...] = (
    MEM_TYPE_IDENTITY, MEM_TYPE_RELATIONSHIP, MEM_TYPE_SECRET,
)
#: tier 1 关键词（硬信号）：**不可逆**事件 —— 发生就不可撤销
TIER1_HARD_KEYWORDS: Tuple[str, ...] = (
    "死", "去世", "杀了", "杀害", "牺牲", "自杀", "残疾", "失忆",
    "怀孕", "结婚", "离婚", "告白", "背叛", "毁容", "破产", "断绝关系",
)
#: tier 1 关键词（软信号）：身份 / 核心关系
TIER1_RELATION_KEYWORDS: Tuple[str, ...] = (
    "我是", "真正的身份", "真实身份", "其实是", "原来是", "出生于", "亲生",
    "从小", "唯一的", "永远", "再也不", "母亲", "父亲", "妈妈", "爸爸",
    "女儿", "儿子", "姐姐", "妹妹", "哥哥", "弟弟", "妻子", "丈夫", "恋人",
    "未婚妻", "未婚夫", "师父", "主人", "契约", "婚约",
)
#: 兼容别名（老写法）：所有 tier1 关键词
TIER1_KEYWORDS: Tuple[str, ...] = (
    TIER1_HARD_KEYWORDS + TIER1_RELATION_KEYWORDS
)
#: tier 4 关键词：当前情绪 / 动作 / 场景（瞬时，随时会过期）
TIER4_KEYWORDS: Tuple[str, ...] = (
    "此刻", "现在", "刚刚", "刚才", "正在", "暂时", "眼下", "今天",
    "哭", "笑", "生气", "害怕", "紧张", "开心", "难过", "委屈", "害羞",
    "累", "饿", "困", "冷", "热", "疼",
    "坐下", "站起", "走进", "走出", "拿起", "放下", "递给", "看着",
    "房间", "走廊", "窗外", "桌上", "门口", "杯", "茶", "饭",
)

# ---- 指数衰减 D(t) = D_0 * exp(-lambda_D * delta_t)（[V6 阶段B]）----
LAMBDA_BASE = 0.01          # 基础衰减率（= 旧的 config.memory.decay_rate 默认值）
DECAY_ALPHA = 0.5           # 情感残留 emotional_residue 的减速权重
DECAY_BETA = 0.5            # 巩固度 consolidation 的减速权重
DECAY_GAMMA = 0.3           # 干扰 interference 的加速权重
DEFAULT_CONSOLIDATION = 0.1  # 新建记忆的 consolidation 初值
#: 距上次「结算时间」不足这么多分钟就不结算（避免空转刷时间戳）
DECAY_MIN_DELTA_MINUTES = 1.0

# ---- 生命周期阈值 / 唤醒 / 巩固（[V6 阶段B + C]）----
MEM_DORMANT_THRESHOLD = 0.05     # strength < 0.05 -> dormant
#: （0.15 沿用既有常量 MEM_WEAKEN_THRESHOLD）
DORMANT_WAKE_BOOST = 0.2         # 命中关键词唤醒 DORMANT：strength += 0.2
#: 唤醒的相关度门槛：提问 token 至少有这一比例出现在休眠记忆里才唤醒
DORMANT_WAKE_MIN_REL = 0.2
#: 一次检索最多唤醒几条
DORMANT_WAKE_MAX = 5
CONSOLIDATION_BUMP = 0.05        # 每被注入一次 Prompt：consolidation += 0.05
CONSOLIDATION_MAX = 1.0

# ---- ContextBuilder 的 Token 预算（[V6 阶段C]）----
#: 记忆区块的 Token 预算（可被 config.memory.context_token_budget 覆盖）
CONTEXT_TOKEN_BUDGET = 3000
#: 剩余预算按 40% / 30% / 20% 分配给 tier2 / tier3 / tier4
#: （tier1 核心记忆优先注入，不参与比例分配）
TIER_BUDGET_RATIO: Dict[int, float] = {2: 0.40, 3: 0.30, 4: 0.20}
#: 总输出字数的最后兜底上限（可被 config.memory.context_max_chars 覆盖）
CONTEXT_MAX_CHARS_DEFAULT = 24000

# ---- 【阶段 D】安全聚合合并 ----
MERGE_INTERVAL_MIN = 120                 # 自动合并周期：2 小时
SIMILAR_THRESHOLD = 0.7                  # difflib 粗筛相似度阈值
MERGE_MAX_PER_RUN = 200                  # 本轮最多扫描 200 条记忆
MERGE_MAX_CANDIDATES = 50                # 本轮最多产出 50 个候选组
MERGE_MAX_GROUP_SIZE = 5                 # 单组最多合并 5 条
MERGE_MIN_GROUP_SIZE = 2                 # 最少 2 条才合并
TEXT_TRUNCATE_LEN = 500                  # 粗筛比对前文本截断（性能保护，保持不变）
#: 终审（喂给 LLM）时允许更长的正文：粗筛用 500 字，终审用 1000 字，
#: 避免「矛盾信息落在 500 字之后」被截掉导致 LLM 误判。
MERGE_VERDICT_TRUNCATE_LEN = 1000
MERGE_TIME_WINDOW_DAYS = 30              # 时间窗口（天）
#: 新生成摘要记忆的状态 / 旧记忆被压掉后的状态（**绝不物理删除**）
MERGE_NEW_STATUS = MEM_STATUS_ACTIVE
MERGE_OLD_STATUS = MEM_STATUS_WEAKENED
#: 合并摘要记忆的标签
MERGE_TAG = "merge"
#: 新记忆 consolidation 取值比例：consolidation = max(组内均值, 组内最大值 × 0.8)
MERGE_CONSOLIDATION_RATIO = 0.8
#: 合并后台线程名（日志/排障用）
MERGE_THREAD_NAME = "memory-merge"

# ---- 【阶段 D】互斥与调度器：全局状态（模块级，进程内唯一）----
_merge_lock = threading.Lock()
_merge_running = False
_scheduler_lock = threading.Lock()
_merge_timer: Optional[Any] = None
#: 最近一次合并的结果摘要（Web /api/merge_status 用；不落库）
_merge_last_result: Dict[str, Any] = {}
_merge_last_at: str = ""

# ---- [relations-5] 状态句滞后带：档位缓存（纯内存，进程内；重启自然清空）----
_rel_band_cache: Dict[Any, int] = {}
_rel_band_lock = threading.Lock()


def _rel_band(key: Any, value: float, hi: float, lo: float) -> int:
    """[relations-5] 带滞后带的档位判定：2=高档，1=低档，0=无。

    已在高档 -> ``value >= hi - BUFFER`` 维持高档；
    已在低档 -> ``value <= lo + BUFFER`` 维持低档；
    否则重新判定：进高档要 ``>= hi + BUFFER``，进低档要 ``<= lo - BUFFER``。
    ``lo < 0`` 表示该维度没有低档。**只读数值，不回写数据库。**
    """
    try:
        with _rel_band_lock:
            prev = _rel_band_cache.get(key)
    except Exception:
        prev = None
    cur = 0
    if prev == 2 and value >= hi - REL_BAND_BUFFER:
        cur = 2
    elif prev == 1 and lo >= 0 and value <= lo + REL_BAND_BUFFER:
        cur = 1
    elif value >= hi + REL_BAND_BUFFER:
        cur = 2
    elif lo >= 0 and value <= lo - REL_BAND_BUFFER:
        cur = 1
    if cur != prev:
        try:
            with _rel_band_lock:
                _rel_band_cache[key] = cur
                while len(_rel_band_cache) > REL_BAND_CACHE_MAX:
                    _rel_band_cache.pop(next(iter(_rel_band_cache)))
        except Exception:
            pass
    return cur


# ---- [relations-8/9] 强状态重申 + 弱信号累积：进程内状态（重启即丢）----
_rel_turn_counter: int = 0
_rel_affirm_state: Dict[Any, Dict[str, Any]] = {}
_rel_affirm_lock = threading.Lock()
_rel_pending_signals: Dict[Any, List[float]] = {}
_rel_unset_cache: Dict[Any, set] = {}
_rel_pending_lock = threading.Lock()


def _rel_turn_bump() -> int:
    """[relations-8] 每跑一次 build() 记一轮。"""
    global _rel_turn_counter
    _rel_turn_counter += 1
    return _rel_turn_counter


def _rel_row_should_emit(row: Dict[str, Any]) -> bool:
    """[relations-8] 这条关系本轮该不该注入。

    * 行有变动（``updated_at`` 变了）-> 注入
    * 否则看强状态：hate / dep / trust 到阈值，每 N 轮强制重申一次
    * 都不满足 -> 本轮不注入
    任何异常一律返回 True（宁可多注入，不可丢关系）。
    """
    try:
        key = row.get("rel_id")
        if key is None:
            key = "%s>%s" % (row.get("from_character_id"),
                             row.get("to_character_id"))
        updated = row.get("updated_at")
        turn = _rel_turn_counter
        emit = False
        with _rel_affirm_lock:
            for dim, th, period in REL_WATCH_DIMS:
                try:
                    v = float(row.get(dim) or 0.0)
                except Exception:
                    v = 0.0
                if v <= th:
                    continue
                k = "%s|%s" % (key, dim)
                st = _rel_affirm_state.get(k) or {}
                if st.get("updated_at") != updated:
                    emit = True
                elif (turn - int(st.get("last_turn", -10 ** 9))) >= (period - 1):
                    emit = True
                if emit:
                    _rel_affirm_state[k] = {"updated_at": updated,
                                            "last_turn": turn}
                    break
            if not emit:
                k0 = "%s|__row__" % key
                st0 = _rel_affirm_state.get(k0) or {}
                if st0.get("updated_at") != updated:
                    emit = True
            if emit:
                _rel_affirm_state["%s|__row__" % key] = {
                    "updated_at": updated, "last_turn": turn}
                while len(_rel_affirm_state) > REL_AFFIRM_CACHE_MAX:
                    _rel_affirm_state.pop(next(iter(_rel_affirm_state)))
        return emit
    except Exception:
        return True
@dataclass

# ══════════════════════════════════════════════════════════════════════
# 【04】配置层
# ══════════════════════════════════════════════════════════════════════

class LLMConfig:
    """OpenAI 兼容接口配置（SPEC「LLM 客户端」段）。"""

    enabled: bool = False
    base_url: str = LLM_DEFAULT_BASE_URL
    api_key: str = LLM_DEFAULT_API_KEY
    model: str = LLM_DEFAULT_MODEL
    temperature: float = LLM_DEFAULT_TEMPERATURE
    max_tokens: int = LLM_DEFAULT_MAX_TOKENS
    temperature: float = LLM_DEFAULT_TEMPERATURE
    max_tokens: int = LLM_DEFAULT_MAX_TOKENS
    timeout: float = LLM_DEFAULT_TIMEOUT

    # ---- 批 6 追加：本地 OpenAI 兼容中继（Tavo / SillyTavern 直连）----
    #: 中继模式默认角色（调用方没给 ?char= / X-Character 时用它）
    default_character: str = ""
    #: 中继是否注入记忆上下文；false 时退化为纯转发（不注入、不需要角色）
    inject_memory: bool = True

    # ---- 批 10 追加：边聊边记 ----
    #: true = 中继转发成功后把这一轮写进 messages 表并抽取记忆（不用手动 import）
    auto_ingest: bool = True
    # ---- [V6 阶段A] 追加：异步回写 ----
    #: true  = 回写 / 抽取在后台 daemon 线程里做，绝不阻塞用户看到回复
    #: false = 退回「转发完就地回写」（排障用）
    ingest_async: bool = True

    # ---- V3 追加：卡片层 ----
    #: 中继第 5 级兜底用的默认卡名（识别不出卡时用它；留空 = 不兜底）
    default_card: str = ""
    #: true = 本地扫描全都认不出时，调一次 LLM 兜底识别卡 / 说话人
    auto_detect_card: bool = True

    # ---- V4 追加：延迟一拍写库（reroll 的旧版本永不入库）----
    #: true = 转发成功后只把这一轮**暂存**到 conversation_meta，
    #:        等下一次请求（user 消息变了 / 超时）才真正落库并抽取。
    #:        false = 退回批 10 的旧行为（转发成功立即写库）。
    deferred_ingest: bool = True
    #: 暂存超过这个秒数，下一次请求就先把暂存落库（默认 600 = 10 分钟）
    stage_commit_timeout: float = 600.0

    def endpoint(self) -> str:
        """规范化出 /chat/completions 完整地址（自动补 http:// 前缀）。"""
        base = (self.base_url or "").strip().rstrip("/")
        if not base:
            base = LLM_DEFAULT_BASE_URL
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        return base + "/chat/completions"

    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def usable(self) -> bool:
        """配置上是否具备调用条件（不看 enabled 开关）。"""
        return bool(str(self.base_url or "").strip()
                    and str(self.model or "").strip())


@dataclass
class MemoryConfig:
    """记忆引擎可调参数（SPEC「配置」段 memory 小节 + 内部阈值）。"""

    # ---- SPEC 配置文件的 memory 段 ----
    extraction_interval: int = 10
    max_context_memories: int = 20
    decay_enabled: bool = True
    decay_rate: float = MEM_BASE_DECAY_RATE
    consolidate_threshold: int = 5
    auto_detect_main: bool = True
    #: [V2.5 卡牌强制主角] true = 卡一旦定下来，说话人**强制锁定**为这张卡的
    #: ``main_character``（忽略 Tavo 传过来的任何称呼）；卡下没有绑定主角色时
    #: 才退回别名映射。默认 false（保守），在 config.yaml 的 memory 段打开。
    enforce_card_main_character: bool = False

    # ---- 衰减 ----
    importance_slowdown: float = DECAY_IMPORTANCE_SLOWDOWN
    emotion_slowdown: float = DECAY_EMOTION_SLOWDOWN
    weaken_threshold: float = MEM_WEAKEN_THRESHOLD

    # ---- 检索 ----
    retrieve_default_limit: int = RETRIEVE_DEFAULT_LIMIT
    retrieve_min_score: float = RETRIEVE_MIN_SCORE

    # ---- V6 阶段C 追加：Token 预算（废除 20 条 / 6000 字硬编码）----
    #: 记忆区块可用的 Token 预算（tier1 优先注入，剩余按 40/30/20 分给
    #: tier2/3/4）。<=0 时退回旧的「按条数取」行为。
    context_token_budget: int = CONTEXT_TOKEN_BUDGET
    #: 整份上下文文本的最后兜底字数上限（旧值是硬编码 6000）
    context_max_chars: int = CONTEXT_MAX_CHARS_DEFAULT
    #: 检索时是否启用「高相关唤醒」（命中关键词的 DORMANT 记忆改回 ACTIVE）
    dormant_wakeup: bool = True
    #: 记忆被注入 Prompt 时是否累加 consolidation（+0.05）
    consolidation_bump: bool = True

    # ---- V6 阶段B 追加：指数衰减（LAMBDA_BASE 见 DECAY_* 常量）----
    decay_alpha: float = DECAY_ALPHA
    decay_beta: float = DECAY_BETA
    decay_gamma: float = DECAY_GAMMA
    dormant_threshold: float = MEM_DORMANT_THRESHOLD

    # ---- V6 阶段D 追加：自动聚合合并调度 ----
    #: true = serve 启动时自动挂上合并调度器（每 MERGE_INTERVAL_MIN 分钟）
    auto_merge: bool = True
    #: 自动合并周期（分钟）
    merge_interval_min: int = MERGE_INTERVAL_MIN
    #: 调度器是否在空闲时自动跑（false = 只留手动 CLI / Web 按钮）
    merge_enabled: bool = True

    # ---- 角色 ----
    main_promote_min_messages: int = MAIN_PROMOTE_MIN_MESSAGES
    main_promote_min_days: float = MAIN_PROMOTE_MIN_DAYS
    active_window_messages: int = ACTIVE_WINDOW_MESSAGES
    active_window_hours: float = ACTIVE_WINDOW_HOURS

    # ---- 容量 ----
    max_memories_per_character: int = MAX_MEMORIES_PER_CHARACTER
    enforce_capacity: bool = ENFORCE_CAPACITY

    # ---- V3 追加：哪些角色算「用户」 ----
    #: 这些名字（以及 ``characters.is_user = 1``）**永远不建记忆**：
    #: 用户（人类玩家）不需要自己的记忆，记忆只服务于 AI 扮演的角色。
    #: 默认只含自动建档用的 ``"User"``（= RELAY_INGEST_USER_NAME，那个常量
    #: 定义在文件后段，类定义期还不能引用，所以这里写字面量）；
    #: 玩家角色真名（如「明」）写进 config.yaml 的 ``memory.user_names``。
    user_names: Tuple[str, ...] = ("User",)

    # ---- 阈值一致性自检 ----
    def max_delta(self) -> float:
        """关系单次调整幅度上限（SPEC 强制校验 7）。"""
        return REL_MAX_DELTA


@dataclass
class Config:
    """引擎总配置。"""

    db_path: str = DEFAULT_DB_PATH
    debug: bool = False
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    log_dir: str = LOG_DIR
    log_file: str = LOG_FILENAME
    source_path: Optional[str] = None

    # ------------------------------------------------------------------
    def validate(self) -> "Config":
        """静态一致性检查；不一致直接抛 ValueError。"""
        errors: List[str] = []
        m = self.memory

        if not str(self.db_path or "").strip():
            errors.append("db_path 不能为空")
        if not str(self.host or "").strip():
            errors.append("host 不能为空")
        if not (0 < int(self.port) < 65536):
            errors.append(f"port 非法：{self.port}")

        if m.decay_rate < 0:
            errors.append("decay_rate 不能为负")
        if m.consolidate_threshold < 2:
            errors.append("consolidate_threshold 必须 >= 2")
        if m.max_context_memories <= 0:
            errors.append("max_context_memories 必须 > 0")
        if m.extraction_interval < 1:
            errors.append("extraction_interval 必须 >= 1")
        if m.retrieve_default_limit <= 0:
            errors.append("retrieve_default_limit 必须 > 0")
        if m.main_promote_min_messages < 0:
            errors.append("main_promote_min_messages 不能为负")

        if self.llm.temperature < 0:
            errors.append("llm.temperature 不能为负")
        if self.llm.max_tokens <= 0:
            errors.append("llm.max_tokens 必须 > 0")
        if self.llm.timeout <= 0:
            errors.append("llm.timeout 必须 > 0")

        if errors:
            raise ValueError("配置校验失败：" + "；".join(errors))
        return self

    def to_dict(self) -> Dict[str, Any]:
        """导出为纯 dict。"""
        return asdict(self)

    def describe(self) -> Dict[str, Any]:
        """人类可读摘要（不含密钥）。"""
        return {
            "app": f"{APP_NAME} v{APP_VERSION}",
            "db_path": self.db_path,
            "host": self.host,
            "port": self.port,
            "debug": self.debug,
            "llm": {
                "enabled": self.llm.enabled,
                "endpoint": self.llm.endpoint(),
                "model": self.llm.model,
            },
            "memory": asdict(self.memory),
        }


    def to_save_dict(self) -> Dict[str, Any]:
        """导出可写回 config.yaml 的 dict（含 api_key）。"""
        return {
            "db_path": self.db_path,
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "llm": asdict(self.llm),
            "memory": asdict(self.memory),
        }

    def save(self, path: Optional[str] = None) -> bool:
        """把当前配置写回 config.yaml。成功返回 True。"""
        import os as _os
        target = str(path or self.source_path or "config.yaml")
        data = self.to_save_dict()
        try:
            if _HAS_YAML:
                import yaml as _yaml
                with open(target, "w", encoding=DEFAULT_ENCODING) as f:
                    _yaml.safe_dump(data, f, allow_unicode=True,
                                    sort_keys=False, default_flow_style=False)
            else:
                import json as _json
                with open(target, "w", encoding=DEFAULT_ENCODING) as f:
                    _json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as ex:
            _get_logger("config").warning("保存配置失败 %s：%s", target, ex)
            try:
                import traceback as _tb
                import os as _os
                _err_path = _os.path.expanduser("~/save_err.log")
                with open(_err_path, "a", encoding="utf-8") as _f:
                    _f.write("=" * 50 + "\n")
                    _f.write("target=%s\n" % target)
                    _f.write(_tb.format_exc())
                    _f.write("\n")
            except Exception:
                pass
            return False


def _load_config_file(path: Union[str, Path]) -> Dict[str, Any]:
    """读取 YAML（优先）或 JSON 配置文件。"""
    p = Path(path)
    raw = p.read_text(encoding=DEFAULT_ENCODING)
    if _HAS_YAML:
        try:
            data = yaml.safe_load(raw)
        except Exception as ex:
            raise ValueError(f"YAML 解析失败 {p}: {ex}") from ex
    else:
        try:
            data = json.loads(raw)
        except Exception as ex:
            raise ValueError(
                f"JSON 解析失败 {p}: {ex}（未安装 pyyaml，只能读 JSON 格式）"
            ) from ex
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件根节点必须是映射/对象，实际为 {type(data).__name__}")
    return data


def _apply_section(target: Any, data: Dict[str, Any],
                   logger: logging.Logger) -> None:
    """把一段 dict 覆盖到 dataclass 上，忽略未知键（仅告警）。"""
    valid = set(target.__dataclass_fields__.keys())
    unknown: List[str] = []
    for key, value in (data or {}).items():
        if key not in valid:
            unknown.append(str(key))
            continue
        setattr(target, key, value)
    if unknown:
        logger.warning("配置含未知字段（已忽略）：%s", ", ".join(sorted(unknown)))


def load_config(path: Optional[Union[str, Path]] = None) -> Config:
    """加载配置，优先级（低 -> 高）：

        1. 代码内默认值
        2. 配置文件：``path`` 参数 > ``config.yaml`` > ``config.yml`` > ``config.json``
        3. 环境变量 ``MEM_*``（便于容器化）

    返回值一定通过 ``validate()``。
    """
    logger = _get_logger("config")
    cfg = Config()

    candidates: List[Path] = []
    if path:
        candidates.append(Path(path))
    else:
        candidates.extend(Path(n) for n in DEFAULT_CONFIG_NAMES)

    data: Dict[str, Any] = {}
    for cand in candidates:
        try:
            if cand.is_file():
                data = _load_config_file(cand)
                cfg.source_path = str(cand.resolve())
                logger.info("已加载配置：%s", cfg.source_path)
                break
        except ValueError:
            raise
        except Exception as ex:
            logger.warning("读取配置失败 %s：%s", cand, ex)

    if data:
        for key in ("db_path", "debug", "host", "port", "log_dir", "log_file"):
            if key in data:
                setattr(cfg, key, data[key])
        if isinstance(data.get("llm"), dict):
            _apply_section(cfg.llm, data["llm"], logger)
        if isinstance(data.get("memory"), dict):
            _apply_section(cfg.memory, data["memory"], logger)
        known = {"db_path", "debug", "host", "port", "log_dir", "log_file",
                 "llm", "memory"}
        for key in data:
            if key not in known:
                logger.warning("配置含未知顶层字段（已忽略）：%s", key)

    # ---- 环境变量覆盖 ----
    if os.environ.get("MEM_DB_PATH"):
        cfg.db_path = os.environ["MEM_DB_PATH"]
    if os.environ.get("MEM_DEBUG"):
        cfg.debug = os.environ["MEM_DEBUG"].strip().lower() in (
            "1", "true", "yes", "y", "on")
    if os.environ.get("MEM_HOST"):
        cfg.host = os.environ["MEM_HOST"]
    if os.environ.get("MEM_PORT"):
        try:
            cfg.port = int(os.environ["MEM_PORT"])
        except Exception:
            logger.warning("MEM_PORT 非法，已忽略：%r", os.environ["MEM_PORT"])
    if os.environ.get("MEM_LLM_BASE_URL"):
        cfg.llm.base_url = os.environ["MEM_LLM_BASE_URL"]
    if os.environ.get("MEM_LLM_API_KEY"):
        cfg.llm.api_key = os.environ["MEM_LLM_API_KEY"]
    if os.environ.get("MEM_LLM_MODEL"):
        cfg.llm.model = os.environ["MEM_LLM_MODEL"]
    if os.environ.get("MEM_LLM_ENABLED"):
        cfg.llm.enabled = os.environ["MEM_LLM_ENABLED"].strip().lower() in (
            "1", "true", "yes", "y", "on")

    cfg.validate()
    return cfg


def hot_reload_config(cfg: "Config", path: Optional[str] = None) -> bool:
    """重新读 config.yaml，把新值拷进现有 cfg 对象的字段（不替换对象）。

    好处：凡持有 cfg 引用的地方都看得到新值，不用重启。
    """
    try:
        new = load_config(path or cfg.source_path)
    except Exception as ex:
        _get_logger("config").warning("热加载失败（保留旧配置）：%s", ex)
        return False
    # 顶层标量
    for f in ("db_path", "debug", "host", "port", "log_dir", "log_file"):
        try:
            setattr(cfg, f, getattr(new, f))
        except Exception:
            pass
    # llm / memory 子段：逐字段覆盖
    for section_name in ("llm", "memory"):
        old_sec = getattr(cfg, section_name)
        new_sec = getattr(new, section_name)
        for f in old_sec.__dataclass_fields__:
            try:
                setattr(old_sec, f, getattr(new_sec, f))
            except Exception:
                pass
    return True


# ==============================================================================
# 完整 SQL Schema —— 从 SPEC.md「完整 SQL Schema」段一字不改照抄
# ==============================================================================

SCHEMA_SQL = """
-- ============================================================================
-- V3 追加：卡片层（cards）。一张"卡" = 一个作品 / 场景 / 设定集，
-- 是 characters 的分组容器。**记忆永远挂 characters，绝不挂 cards。**
-- ============================================================================
CREATE TABLE IF NOT EXISTS cards (
    card_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    source TEXT DEFAULT 'tavo',
    cover TEXT DEFAULT '{}',
    created_at TEXT,
    last_seen TEXT,
    -- [卡片逻辑删除] 1 = 正常；0 = 已删除（**只改标记，绝不删行**）
    is_active INTEGER NOT NULL DEFAULT 1,
    -- [V2.3 别名映射] 卡片别名/关键词（JSON 数组）：Tavo 发来的卡名先比真名、再比别名
    aliases TEXT DEFAULT '[]',
    -- [P0] 从 Tavo system message 抓来的角色设定原文（纯文本，非 JSON）
    persona_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_cards_seen ON cards(last_seen DESC);

CREATE TABLE IF NOT EXISTS characters (
    character_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    role_type TEXT NOT NULL DEFAULT 'unknown',
    is_user INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT, last_seen TEXT,
    message_count INTEGER NOT NULL DEFAULT 0,
    aliases TEXT DEFAULT '[]',
    profile TEXT DEFAULT '{}',
    static_profile TEXT DEFAULT '{}',
    traits TEXT DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1,
    -- [V2.7 彻底移除] NULL = 正常；非空 = 已「彻底移除」：
    -- 从所有 UI 列表消失，但**行与记忆全部留档**（绝不物理删除）
    purged_at TEXT DEFAULT NULL,
    card_id INTEGER REFERENCES cards(card_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    source_file TEXT, source_position INTEGER,
    name TEXT, is_user INTEGER, is_system INTEGER,
    mes TEXT, send_date TEXT,
    character_id INTEGER,
    imported_at TEXT,
    processed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_msg_processed ON messages(processed);
CREATE INDEX IF NOT EXISTS idx_msg_char ON messages(character_id);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    event_type TEXT DEFAULT 'world_event',
    importance REAL DEFAULT 0.5,
    emotional_intensity REAL DEFAULT 0.5,
    occurred_at TEXT,
    location TEXT,
    source_message_ids TEXT DEFAULT '[]',
    is_factual INTEGER NOT NULL DEFAULT 1,
    dedup_hash TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_dedup ON events(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_events_factual ON events(is_factual);

CREATE TABLE IF NOT EXISTS event_visibility (
    vis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    present INTEGER NOT NULL DEFAULT 0,
    role_in_event TEXT,
    state TEXT NOT NULL,
    partial_content TEXT,
    confidence REAL DEFAULT 0.7,
    source TEXT,
    source_message_ids TEXT DEFAULT '[]',
    learned_at TEXT,
    updated_at TEXT,
    interpretation_json TEXT DEFAULT '',  -- [P/E 前置 10-06] 主观诠释 JSON（P3 才写）
    UNIQUE(event_id, character_id)
);
CREATE INDEX IF NOT EXISTS idx_ev_event ON event_visibility(event_id);
CREATE INDEX IF NOT EXISTS idx_ev_char_state ON event_visibility(character_id, state);
CREATE INDEX IF NOT EXISTS idx_ev_char_present ON event_visibility(character_id, present);

CREATE TABLE IF NOT EXISTS memories (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_character_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    memory_type TEXT NOT NULL DEFAULT 'episodic',
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    confidence REAL DEFAULT 0.7,
    emotional_intensity REAL DEFAULT 0.5,
    recall_strength REAL DEFAULT 1.0,
    created_at TEXT,
    last_recalled TEXT,
    recall_count INTEGER NOT NULL DEFAULT 0,
    source_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    source_message_id TEXT,
    source_visibility_id INTEGER REFERENCES event_visibility(vis_id) ON DELETE SET NULL,
    is_subjective INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    is_consolidated INTEGER NOT NULL DEFAULT 0,
    consolidated_from TEXT DEFAULT '[]',
    consolidated_mode TEXT,
    tags TEXT DEFAULT '[]',
    dedup_hash TEXT,
    -- [V6 阶段B] 多维生命周期字段 --
    tier INTEGER NOT NULL DEFAULT 3,          -- 1 核心 / 2 重要 / 3 普通 / 4 瞬时
    emotional_residue REAL NOT NULL DEFAULT 0.0,  -- 情感残留 0..1（衰减减速）
    consolidation REAL NOT NULL DEFAULT 0.1,      -- 巩固度 0..1（衰减减速）
    merged_from TEXT DEFAULT '[]',                -- [V6 阶段D] 被合并掉的旧记忆 id 列表
    source_type TEXT DEFAULT 'UNKNOWN',           -- 记忆来源（USER/OBSERVATION/DIRECTIVE/INFERENCE/HEARSAY/UNKNOWN）
    story_time TEXT DEFAULT ''                    -- 剧情时间戳（用户消息里的"X月X日X时"，空=未指定）
);
CREATE INDEX IF NOT EXISTS idx_mem_owner ON memories(owner_character_id, status);
CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(owner_character_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_mem_hash ON memories(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_mem_event ON memories(source_event_id);
CREATE INDEX IF NOT EXISTS idx_mem_consol ON memories(is_consolidated);
CREATE INDEX IF NOT EXISTS idx_mem_recall ON memories(owner_character_id, recall_strength DESC);

-- knowledge.event_id 为兼容字段；V2 新写入的非事件型 knowledge 默认必须为 NULL。
-- 不得通过 knowledge.event_id 将事件型知识绕过 event_visibility 写入 knowledge。
CREATE TABLE IF NOT EXISTS knowledge (
    knowledge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_character_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    confidence REAL DEFAULT 0.5,
    source TEXT,
    created_at TEXT,
    updated_at TEXT,
    dedup_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_know_owner ON knowledge(owner_character_id, status);
CREATE INDEX IF NOT EXISTS idx_know_hash ON knowledge(dedup_hash);

CREATE TABLE IF NOT EXISTS beliefs (
    belief_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_character_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_ref TEXT,
    statement TEXT NOT NULL,
    confidence REAL DEFAULT 0.7,
    based_on_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    based_on_belief_id INTEGER REFERENCES beliefs(belief_id) ON DELETE SET NULL,
    generated_by TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by INTEGER REFERENCES beliefs(belief_id) ON DELETE SET NULL,
    formed_at TEXT,
    updated_at TEXT,
    tags TEXT DEFAULT '[]',
    dedup_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_belief_owner ON beliefs(owner_character_id, status, kind);
CREATE INDEX IF NOT EXISTS idx_belief_subject ON beliefs(owner_character_id, subject_kind, subject_ref, status);
CREATE INDEX IF NOT EXISTS idx_belief_hash ON beliefs(dedup_hash);

CREATE TABLE IF NOT EXISTS relationships (
    rel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_character_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    to_character_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    trust REAL DEFAULT 0.5,
    affection REAL DEFAULT 0.5,
    resentment REAL DEFAULT 0.0,
    familiarity REAL DEFAULT 0.5,
    respect REAL DEFAULT 0.5,
    fear REAL DEFAULT 0.0,
    dependency REAL DEFAULT 0.0,
    state_summary TEXT,
    updated_at TEXT,
    -- [P0] 0 = 尚未从角色卡抽取初始关系；1 = 已抽取或已放弃
    initialized INTEGER NOT NULL DEFAULT 0,
    UNIQUE(from_character_id, to_character_id)
);
CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_character_id);

CREATE TABLE IF NOT EXISTS relationship_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_character_id INTEGER NOT NULL,
    to_character_id INTEGER NOT NULL,
    field TEXT NOT NULL,
    delta REAL,
    old_value REAL,
    new_value REAL,
    reason TEXT,
    source_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    source_belief_id INTEGER REFERENCES beliefs(belief_id) ON DELETE SET NULL,
    changed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_relh_pair ON relationship_history(from_character_id, to_character_id, changed_at);

CREATE TABLE IF NOT EXISTS character_states (
    character_id INTEGER PRIMARY KEY REFERENCES characters(character_id) ON DELETE CASCADE,
    emotion TEXT, mood TEXT,
    trust REAL DEFAULT 0.5, affection REAL DEFAULT 0.5,
    anger REAL DEFAULT 0.0, fear REAL DEFAULT 0.0, stress REAL DEFAULT 0.0,
    relationship_state TEXT,
    current_goal TEXT, current_location TEXT,
    physical_state TEXT, mental_context TEXT,
    unresolved_conflicts TEXT,
    summary TEXT,
    updated_at TEXT,
    source_type TEXT DEFAULT ''   -- [P/E 前置 10-06] USER_DECLARED / MODEL_EXPLICIT / SYSTEM_DERIVED（E2 才写）
);

CREATE TABLE IF NOT EXISTS state_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT, new_value TEXT,
    reason TEXT,
    source_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    changed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_stateh_char ON state_history(character_id, changed_at);

CREATE TABLE IF NOT EXISTS commitments (
    commitment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    promiser_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    promisee_id INTEGER REFERENCES characters(character_id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    created_at TEXT,
    deadline TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    source_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    notes TEXT,
    dedup_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_com_prom ON commitments(promiser_id, status);
CREATE INDEX IF NOT EXISTS idx_com_ee ON commitments(promisee_id, status);
CREATE INDEX IF NOT EXISTS idx_com_dedup ON commitments(dedup_hash);

CREATE TABLE IF NOT EXISTS secrets (
    secret_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_character_id INTEGER NOT NULL REFERENCES characters(character_id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    subject TEXT,
    revealed_to TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    source_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    created_at TEXT,
    dedup_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_secret_owner ON secrets(owner_character_id, status);

CREATE TABLE IF NOT EXISTS associations (
    assoc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_a INTEGER NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
    memory_b INTEGER NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
    assoc_type TEXT DEFAULT 'related',
    weight REAL DEFAULT 1.0,
    created_at TEXT,
    UNIQUE(memory_a, memory_b, assoc_type)
);
CREATE INDEX IF NOT EXISTS idx_assoc_a ON associations(memory_a);
CREATE INDEX IF NOT EXISTS idx_assoc_b ON associations(memory_b);

CREATE TABLE IF NOT EXISTS event_chains (
    chain_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS event_chain_links (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id INTEGER NOT NULL REFERENCES event_chains(chain_id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    sequence INTEGER,
    prev_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    UNIQUE(chain_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_chain_links ON event_chain_links(chain_id, sequence);

CREATE TABLE IF NOT EXISTS memory_conflicts (
    conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_character_id INTEGER NOT NULL,
    old_memory_id INTEGER REFERENCES memories(memory_id) ON DELETE SET NULL,
    new_memory_id INTEGER REFERENCES memories(memory_id) ON DELETE SET NULL,
    old_belief TEXT, new_belief TEXT,
    status TEXT DEFAULT 'open',
    resolution TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_conf_owner ON memory_conflicts(owner_character_id, status);

CREATE TABLE IF NOT EXISTS conversation_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


# ==============================================================================
# Database —— SQLite 封装
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【05】数据库 + 建档上下文
# ══════════════════════════════════════════════════════════════════════

class Database:
    """SQLite 封装：连接、建表、读写、事务。

    设计要点
    --------
    * 单连接 + ``threading.RLock``，避免多线程各开连接导致 database is locked
    * ``isolation_level=None``（autocommit），成组写入用 ``transaction()``
    * WAL + busy_timeout，读写互不阻塞
    * **所有写入都包 try/except**（SPEC「容错」段）：失败只记日志，不向上抛
    * ``query`` / ``query_one`` 自动把 JSON_COLUMNS 反序列化为 Python 对象
    """

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        *,
        config: Optional[Config] = None,
        timeout: float = SQLITE_TIMEOUT,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if config is not None:
            self.config: Optional[Config] = config
            raw_path = str(config.db_path or DEFAULT_DB_PATH)
        else:
            self.config = None
            raw_path = str(path or DEFAULT_DB_PATH)

        self.logger = logger or _get_logger("db")
        self.timeout = float(timeout)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._tx_depth = 0

        if raw_path == ":memory:":
            self.path_str = raw_path
        else:
            resolved = Path(raw_path).expanduser()
            try:
                if resolved.parent != Path("."):
                    resolved.parent.mkdir(parents=True, exist_ok=True)
            except Exception as ex:
                self.logger.warning("无法创建数据库目录 %s：%s", resolved.parent, ex)
            self.path_str = str(resolved)

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        """惰性建立连接（首次访问时）。"""
        with self._lock:
            if self._conn is None:
                conn = sqlite3.connect(
                    self.path_str,
                    timeout=self.timeout,
                    check_same_thread=False,
                    isolation_level=None,   # autocommit；事务由 transaction() 控制
                )
                conn.row_factory = sqlite3.Row
                self._conn = conn
                self._apply_pragmas()
                self.logger.debug("已连接数据库：%s", self.path_str)
            return self._conn

    def _apply_pragmas(self) -> None:
        """WAL / 外键 / 忙等待；任一项失败只告警。"""
        assert self._conn is not None
        cur = self._conn.cursor()
        try:
            try:
                cur.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}")
            except sqlite3.Error as ex:
                self.logger.warning("设置 journal_mode 失败（继续）：%s", ex)
            for pragma in (
                "PRAGMA foreign_keys = ON",
                f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_MS)}",
                "PRAGMA synchronous = NORMAL",
            ):
                try:
                    cur.execute(pragma)
                except sqlite3.Error as ex:
                    self.logger.warning("执行 %s 失败（继续）：%s", pragma, ex)
        finally:
            cur.close()

    def init_schema(self) -> "Database":
        """建表（幂等），并写入 conversation_meta 里的版本标记。"""
        with self._lock:
            conn = self.conn
            cur = conn.cursor()
            try:
                cur.executescript(SCHEMA_SQL)
            except sqlite3.Error as ex:
                self.logger.error("建表失败：%s", ex)
            finally:
                cur.close()

            # ---- V2.3 追加：老库幂等加 cards.aliases（卡片别名映射）----
            # 新库在上面 SCHEMA_SQL 里已经建过该列，这里会抛
            # "duplicate column name"，按设计吞掉即可。
            try:
                conn.execute("ALTER TABLE cards ADD COLUMN aliases TEXT DEFAULT '[]'")
                self.logger.info("已为 cards 表补齐 aliases 列（V2.3 别名映射）")
            except sqlite3.Error:
                pass

            # ---- V2.7 追加：老库幂等加 characters.purged_at（彻底移除标记）----
            # 新库在上面 SCHEMA_SQL 里已经建过该列，这里会抛
            # "duplicate column name"，按设计吞掉即可。
            try:
                conn.execute(
                    "ALTER TABLE characters ADD COLUMN purged_at TEXT DEFAULT NULL")
                self.logger.info("已为 characters 表补齐 purged_at 列（V2.7 彻底移除标记）")
            except sqlite3.Error:
                pass

            # ---- V3 追加：老库幂等加 characters.card_id ----
            # 新库在上面 SCHEMA_SQL 里已经建过该列，这里会抛
            # "duplicate column name"，按设计吞掉即可。
            try:
                conn.execute(
                    "ALTER TABLE characters ADD COLUMN card_id INTEGER "
                    "REFERENCES cards(card_id)")
                self.logger.info("已为 characters 表补齐 card_id 列（V3 卡片层）")
            except sqlite3.Error:
                pass
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_char_card "
                    "ON characters(card_id)")
            except sqlite3.Error as ex:
                self.logger.warning("创建 idx_char_card 失败：%s", ex)

            # ---- [卡片逻辑删除] 老库幂等补 cards.is_active ----
            # 新库在上面 SCHEMA_SQL 里已经建过该列，这里会抛
            # "duplicate column name"，按设计吞掉即可。
            try:
                conn.execute(
                    "ALTER TABLE cards ADD COLUMN "
                    "is_active INTEGER NOT NULL DEFAULT 1")
                self.logger.info("已为 cards 表补齐 is_active 列（卡片逻辑删除用）")
            except sqlite3.Error:
                pass

            # ---- [P0] 老库幂等补 cards.persona_text（角色卡设定原文）----
            try:
                conn.execute(
                    "ALTER TABLE cards ADD COLUMN persona_text TEXT")
                self.logger.info("已为 cards 表补齐 persona_text 列（P0 卡文本）")
            except sqlite3.Error:
                pass

            # ---- [P0] 老库幂等补 relationships.initialized ----
            try:
                conn.execute(
                    "ALTER TABLE relationships ADD COLUMN "
                    "initialized INTEGER NOT NULL DEFAULT 0")
                self.logger.info("已为 relationships 表补齐 initialized 列（P0）")
            except sqlite3.Error:
                pass

            # ---- [relations-7a] 老库幂等补 hate_peak / hate_floor_ratio ----
            try:
                conn.execute(
                    "ALTER TABLE relationships ADD COLUMN "
                    "hate_peak REAL DEFAULT 0.0")
                self.logger.info("已为 relationships 表补齐 hate_peak 列（怨恨峰值）")
            except sqlite3.Error:
                pass
            try:
                conn.execute(
                    "ALTER TABLE relationships ADD COLUMN "
                    "hate_floor_ratio REAL DEFAULT 0.15")
                self.logger.info("已为 relationships 表补齐 hate_floor_ratio 列（残留下限）")
            except sqlite3.Error:
                pass

            # ---- 增量：老库幂等补 memories.source_type ----
            try:
                conn.execute(
                    "ALTER TABLE memories ADD COLUMN "
                    "source_type TEXT DEFAULT 'UNKNOWN'")
                self.logger.info("已为 memories 表补齐 source_type 列（记忆来源）")
            except sqlite3.Error:
                pass
            # 旧记忆没有明确来源 -> 统一 UNKNOWN（绝不猜成 USER）
            try:
                _cur = conn.execute(
                    "UPDATE memories SET source_type = 'UNKNOWN' "
                    "WHERE source_type IS NULL OR source_type = ''")
                _n = int(_cur.rowcount) if _cur is not None else 0
                if _n > 0:
                    self.logger.info("已把 %d 条旧记忆的 source_type 回填为 UNKNOWN", _n)
            except sqlite3.Error as ex:
                self.logger.warning("source_type 回填失败（忽略，不影响启动）：%s", ex)

            # ---- V6 阶段B：老库幂等补 memories 的 4 个生命周期字段 ----
            # 新库在上面的 SCHEMA_SQL 里已经建过这些列，这里会抛
            # "duplicate column name"，按设计吞掉即可。
            for _ddl in (
                "ALTER TABLE memories ADD COLUMN tier INTEGER NOT NULL DEFAULT 3",
                "ALTER TABLE memories ADD COLUMN emotional_residue REAL NOT NULL DEFAULT 0.0",
                "ALTER TABLE memories ADD COLUMN consolidation REAL NOT NULL DEFAULT 0.1",
                "ALTER TABLE memories ADD COLUMN merged_from TEXT DEFAULT '[]'",
            ):
                try:
                    conn.execute(_ddl)
                    self.logger.info("已为 memories 表补齐列（V6）：%s",
                                     _ddl.split("ADD COLUMN")[-1].strip()[:40])
                except sqlite3.Error:
                    pass
            # ---- 剧情时间戳：老库幂等补 memories.story_time ----
            try:
                conn.execute(
                    "ALTER TABLE memories ADD COLUMN story_time TEXT DEFAULT ''")
                self.logger.info("已为 memories 表补齐 story_time 列（剧情时间）")
            except sqlite3.Error:
                pass

            # ---- P/E 前置（10-06）：event_visibility.interpretation_json 幂等补列 ----
            try:
                conn.execute(
                    "ALTER TABLE event_visibility ADD COLUMN interpretation_json TEXT DEFAULT ''")
                self.logger.info("已为 event_visibility 表补齐 interpretation_json 列（P/E 主观诠释）")
            except sqlite3.Error:
                pass

            # ---- P/E 前置（10-06）：character_states.source_type 幂等补列 ----
            try:
                conn.execute(
                    "ALTER TABLE character_states ADD COLUMN source_type TEXT DEFAULT ''")
                self.logger.info("已为 character_states 表补齐 source_type 列（E2 状态来源）")
            except sqlite3.Error:
                pass

            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mem_tier "
                    "ON memories(owner_character_id, tier)")
            except sqlite3.Error as ex:
                self.logger.warning("创建 idx_mem_tier 失败：%s", ex)

            self.set_meta("schema_version", str(SCHEMA_VERSION))
            self.set_meta("app_version", APP_VERSION)
        self.logger.info("Schema 就绪（v%d）：%s", SCHEMA_VERSION, self.path_str)
        return self

    # ------------------------------------------------------------------
    # 写入（全部包 try/except）
    # ------------------------------------------------------------------
    def execute(self, sql: str, params: Any = ()) -> Optional[sqlite3.Cursor]:
        """执行单条写语句；失败记日志并返回 None（不抛异常）。"""
        with self._lock:
            try:
                cur = self.conn.execute(sql, tuple(params or ()))
                return cur
            except sqlite3.Error as ex:
                self.logger.error("SQL 执行失败：%s | %s", ex, sql.strip()[:160])
                return None
            except Exception as ex:
                self.logger.error("SQL 执行异常：%s | %s", ex, sql.strip()[:160])
                return None

    def executemany(self, sql: str, seq_of_params: Any) -> Optional[sqlite3.Cursor]:
        """批量执行同一条语句；失败记日志并返回 None。"""
        rows = [tuple(p or ()) for p in (seq_of_params or [])]
        if not rows:
            return None
        with self._lock:
            try:
                return self.conn.executemany(sql, rows)
            except sqlite3.Error as ex:
                self.logger.error("批量 SQL 失败：%s | %s", ex, sql.strip()[:160])
                return None

    def insert(self, sql: str, params: Any = ()) -> Optional[int]:
        """执行 INSERT 并返回新行 id（失败返回 None）。"""
        cur = self.execute(sql, params)
        if cur is None:
            return None
        rowid = cur.lastrowid
        return int(rowid) if rowid is not None else None

    @contextmanager
    def transaction(self) -> Iterator["Database"]:
        """成组事务：成功 COMMIT，异常 ROLLBACK（可重入）。"""
        with self._lock:
            outermost = self._tx_depth == 0
            if outermost:
                try:
                    self.conn.execute("BEGIN IMMEDIATE")
                except sqlite3.Error as ex:
                    self.logger.error("开启事务失败：%s", ex)
                    raise
            self._tx_depth += 1
            try:
                yield self
            except Exception:
                self._tx_depth = max(0, self._tx_depth - 1)
                if outermost:
                    try:
                        self.conn.execute("ROLLBACK")
                    except sqlite3.Error as ex:
                        self.logger.error("事务回滚失败：%s", ex)
                raise
            else:
                self._tx_depth = max(0, self._tx_depth - 1)
                if outermost:
                    try:
                        self.conn.execute("COMMIT")
                    except sqlite3.Error as ex:
                        self.logger.error("事务提交失败：%s", ex)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @staticmethod
    def _decode(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        """sqlite3.Row -> dict，并把 JSON 列反序列化。"""
        if row is None:
            return None
        data: Dict[str, Any] = dict(row)
        for col in JSON_COLUMNS:
            if col in data and isinstance(data[col], str):
                parsed = _parse_json_safe(data[col], None)
                if parsed is not None:
                    data[col] = parsed
        return data

    def query(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        """查询多行，返回 dict 列表（失败返回空列表）。"""
        with self._lock:
            try:
                cur = self.conn.execute(sql, tuple(params or ()))
                rows = cur.fetchall()
            except sqlite3.Error as ex:
                self.logger.error("查询失败：%s | %s", ex, sql.strip()[:160])
                return []
        return [d for d in (self._decode(r) for r in rows) if d is not None]

    def query_one(self, sql: str, params: Any = ()) -> Optional[Dict[str, Any]]:
        """查询单行，无结果或失败返回 None。"""
        with self._lock:
            try:
                cur = self.conn.execute(sql, tuple(params or ()))
                row = cur.fetchone()
            except sqlite3.Error as ex:
                self.logger.error("查询失败：%s | %s", ex, sql.strip()[:160])
                return None
        return self._decode(row)

    def scalar(self, sql: str, params: Any = (), default: Any = 0) -> Any:
        """取单个标量值。"""
        row = self.query_one(sql, params)
        if not row:
            return default
        try:
            return list(row.values())[0]
        except Exception:
            return default

    def count(self, table: str, where: str = "", params: Any = ()) -> int:
        """统计行数（表名白名单校验，防注入）。"""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
            raise ValueError(f"非法表名：{table!r}")
        sql = f"SELECT COUNT(*) AS c FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(self.scalar(sql, params, 0) or 0)

    def table_names(self) -> List[str]:
        """列出全部表名。"""
        return [str(r["name"]) for r in self.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]

    def columns_of(self, table: str) -> List[str]:
        """列出某表的列名。"""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
            raise ValueError(f"非法表名：{table!r}")
        return [str(r["name"]) for r in self.query(f"PRAGMA table_info({table})")]

    # ------------------------------------------------------------------
    # conversation_meta（键值）
    # ------------------------------------------------------------------
    def set_meta(self, key: str, value: Any) -> bool:
        """写入 conversation_meta。"""
        cur = self.execute(
            "INSERT INTO conversation_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(key), str(value)),
        )
        return cur is not None

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """读取 conversation_meta。"""
        row = self.query_one(
            "SELECT value FROM conversation_meta WHERE key = ?", (str(key),))
        return str(row["value"]) if row and row.get("value") is not None else default

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def close(self) -> None:
        """关闭连接（幂等）。"""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error as ex:
                    self.logger.warning("关闭数据库出错：%s", ex)
                finally:
                    self._conn = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<Database path={self.path_str!r} connected={self._conn is not None}>"


# ==============================================================================
# CharacterManager —— 角色注册 + 自动识别 + 活跃角色判断
# ==============================================================================

class CreationContext:
    """★建档裁决上下文（2026-09-21 引入）。

    「谁有资格变成一个角色」从此只有一处裁决 —— ``CharacterManager.resolve_or_reject``。
    本对象就是那次裁决要用的全部证据：

      * ``speakers``   —— 本轮**真实说过话**的人（注入窗口的说话人集合，含玩家）
      * ``declared``   —— 客户端**本轮显式声明**过的名字（卡开场白的【演员】/【女主】名单等）
      * ``card_names`` —— 本卡**现有**角色名 + 别名
      * ``user_names`` —— 玩家真名（config.memory.user_names ∪ 本轮【user】=）

    【为什么】历史教训：LLM 的每一个输出字段（owner_name / visibility.character /
    relationship.from|to / knowledge.owner …）都是一次「凭一个字符串凭空建档」的机会。
    实测 LLM 在窗口里没有真实对话时凭空编出 13 个角色；也实测过把用户自己的第一人称
    经历判给另一个角色。根因不是某条规则写错，而是**建档这条路有十来个入口，
    每个都不校验来源** —— 于是「谁猜错，谁就造幽灵」。
    """

    __slots__ = ("speakers", "declared", "card_names", "user_names")

    @staticmethod
    def _norm(values) -> set:
        out = set()
        for v in (values or ()):
            s = str(v or "").strip()
            if s:
                out.add(s)
        return out

    def __init__(self, speakers=None, declared=None, card_names=None,
                 user_names=None) -> None:
        self.speakers = self._norm(speakers)
        self.declared = self._norm(declared)
        self.card_names = self._norm(card_names)
        self.user_names = self._norm(user_names)


# ══════════════════════════════════════════════════════════════════════
# 【06】角色管理
# ══════════════════════════════════════════════════════════════════════

class CharacterManager:
    """角色的注册、解析、属性维护与活跃度判断。

    唯一键是 ``characters.name``（schema 里 UNIQUE）。
    「新增角色不需要修改代码」：任何没见过的名字都会自动注册。
    """

    def __init__(
        self,
        db: Database,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.config = config
        self.memory_cfg: MemoryConfig = (
            config.memory if config is not None else MemoryConfig()
        )
        self.logger = logger or _get_logger("characters")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_role_type(role_type: Any) -> str:
        rt = str(role_type or DEFAULT_ROLE_TYPE).strip().lower()
        if rt not in VALID_ROLE_TYPES:
            raise ValueError(
                f"非法 role_type：{role_type!r}，应为 {VALID_ROLE_TYPES} 之一")
        return rt

    def _fetch_by_id(self, character_id: Any) -> Optional[Dict[str, Any]]:
        cid = _to_int(character_id)
        if cid is None:
            return None
        return self.db.query_one(
            "SELECT * FROM characters WHERE character_id = ?", (cid,))

    # ------------------------------------------------------------------
    # 注册 / 解析
    # ------------------------------------------------------------------
    def get_or_create(
        self,
        name: Any,
        role_type: Optional[str] = None,
        is_user: bool = False,
        aliases: Optional[Sequence[Any]] = None,
        profile: Optional[Dict[str, Any]] = None,
        static_profile: Optional[Dict[str, Any]] = None,
        traits: Optional[Sequence[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """按名字取角色，不存在则自动注册；返回角色 dict（失败返回 None）。

        * ``role_type=None``      -> 已存在时不改身份，新建时用 ``main_character``
        * ``is_user=True``        -> 建号时把 role_type 定为 ``user``
        * ``aliases`` / ``traits`` -> 与已有值合并去重
        * ``profile`` / ``static_profile`` -> 传值才覆盖
        """
        clean = _bounded_str(name, NAME_MAX_LEN)
        if not clean:
            self.logger.warning("[角色] 拒绝：名字为空")
            return None

        now = now_iso()
        incoming_aliases: List[str] = []
        for a in (aliases or []):
            sa = _bounded_str(a, ALIAS_MAX_LEN)
            if sa and sa != clean and sa not in incoming_aliases:
                incoming_aliases.append(sa)
            if len(incoming_aliases) >= ALIAS_MAX_COUNT:
                break
        incoming_traits = [str(t) for t in (traits or []) if str(t).strip()]

        existing = self.db.query_one(
            "SELECT * FROM characters WHERE name = ?", (clean,))

        if existing is None:
            rt = self._validate_role_type(role_type)
            if is_user and role_type is None:
                rt = ROLE_USER
            new_id = self.db.insert(
                "INSERT INTO characters "
                "(name, role_type, is_user, first_seen, last_seen, message_count, "
                " aliases, profile, static_profile, traits, active) "
                "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 1)",
                (
                    clean, rt, 1 if is_user else 0, now, now,
                    _json_dumps(incoming_aliases),
                    _json_dumps(_as_dict(profile)),
                    _json_dumps(_as_dict(static_profile)),
                    _json_dumps(incoming_traits),
                ),
            )
            if new_id is None:
                # 并发插入：回查一次
                return self.db.query_one(
                    "SELECT * FROM characters WHERE name = ?", (clean,))
            self.logger.info("[角色] 新建 %s（id=%s, role_type=%s, is_user=%s）",
                             clean, new_id, rt, bool(is_user))
            return self._fetch_by_id(new_id)

        # ---- 已存在：合并而非覆盖 ----
        changed = False

        merged_aliases = [str(a) for a in _as_list(existing.get("aliases"))]
        for a in incoming_aliases:
            if a not in merged_aliases and len(merged_aliases) < ALIAS_MAX_COUNT:
                merged_aliases.append(a)
                changed = True
        if clean not in merged_aliases and len(merged_aliases) < ALIAS_MAX_COUNT:
            merged_aliases.append(clean)
            changed = True

        merged_traits = [str(t) for t in _as_list(existing.get("traits"))]
        for t in incoming_traits:
            if t not in merged_traits:
                merged_traits.append(t)
                changed = True

        new_rt = str(existing.get("role_type") or DEFAULT_ROLE_TYPE)
        if role_type is not None:
            rt_in = self._validate_role_type(role_type)
            if rt_in != new_rt:
                new_rt = rt_in
                changed = True
        if is_user and int(existing.get("is_user") or 0) != 1:
            changed = True

        new_profile = (dict(profile) if profile is not None
                       else _as_dict(existing.get("profile")))
        if profile is not None and _as_dict(existing.get("profile")) != new_profile:
            changed = True
        new_static = (dict(static_profile) if static_profile is not None
                      else _as_dict(existing.get("static_profile")))
        if static_profile is not None and \
                _as_dict(existing.get("static_profile")) != new_static:
            changed = True

        sets = ["last_seen = ?"]
        params: List[Any] = [now]
        if changed:
            sets.extend(["aliases = ?", "traits = ?", "role_type = ?",
                         "profile = ?", "static_profile = ?", "is_user = ?"])
            params.extend([
                _json_dumps(merged_aliases), _json_dumps(merged_traits), new_rt,
                _json_dumps(new_profile), _json_dumps(new_static),
                1 if (is_user or int(existing.get("is_user") or 0) == 1) else 0,
            ])
        params.append(int(existing["character_id"]))
        self.db.execute(
            f"UPDATE characters SET {', '.join(sets)} WHERE character_id = ?",
            tuple(params))

        refreshed = self._fetch_by_id(existing["character_id"])
        return refreshed if refreshed is not None else existing

    def resolve_or_reject(
        self,
        name,
        card_id=None,
        ctx=None,
        caller: str = "",
    ):
        """★唯一建档入口：裁决一个名字有没有资格成为角色（2026-09-21）。

        裁决顺序（命中即返回 ``character_id``）：

          1) 命中 ``ctx.user_names``   → 返回**用户**的 id（不建档）
          2) 本卡已有角色 / 别名（其次全局名字 / 别名）→ 返回该 id（不建档）
          3) 客户端本轮**显式声明**过   → 允许创建
          4) 本轮**真实消息里出现过**   → 允许创建
          5) 全否                      → 返回 ``None`` + WARNING ``[建档拒绝]``

        **LLM 的输出只能引用、不能创建**：它给的名字只有落在 3/4 里才会被建出来。
        ``ctx`` 为 ``None`` 时只允许 1/2（查得到就返回，查不到一律拒绝）——
        宁可退化（少记一条），也不要凭空建一个角色。

        ``caller`` 只用于日志，标明是哪个字段触发的拒绝。
        """
        clean = _bounded_str(name, NAME_MAX_LEN)
        if not clean:
            return None
        who = str(caller or "?").strip() or "?"
        speakers = getattr(ctx, "speakers", None) or set()
        declared = getattr(ctx, "declared", None) or set()
        card_names = getattr(ctx, "card_names", None) or set()
        user_names = getattr(ctx, "user_names", None) or set()

        # ---- 1) 玩家真名 → 返回用户 id，不建档（与用户幽灵守卫同一道闸）----
        if clean in user_names:
            try:
                ur = self.get_user()
            except Exception:
                ur = None
            uid = _to_int((ur or {}).get("character_id"))
            if uid is not None:
                self.logger.debug(
                    "[建档] %r 命中玩家真名 → 用户 id=%s（不建档，来源=%s）",
                    clean, uid, who)
                return uid

        # ---- 2) 已经有这个角色 → 复用，绝不新建 ----
        if clean in card_names:
            cid = self.resolve_id(clean)
            if cid is not None:
                return cid
        if card_id is not None:
            try:
                _row = self.db.query_one(
                    "SELECT character_id FROM characters "
                    "WHERE name = ? AND card_id = ?", (clean, int(card_id)))
            except Exception:
                _row = None
            if _row:
                return int(_row["character_id"])
        cid = self.resolve_id(clean)
        if cid is not None:
            return cid

        # ---- 3/4) 有资格创建：客户端显式声明 或 本轮真实出现过 ----
        if clean not in declared and clean not in speakers:
            self.logger.warning(
                "[建档拒绝] name=%s 来源=%s（既不在本轮说话人/客户端声明里，"
                "也不在本卡名单里）", clean, who)
            return None

        src = "客户端声明" if clean in declared else "本轮消息"
        row = self.get_or_create(clean)
        if row is None:
            self.logger.warning("[建档] %r 创建失败（来源=%s）", clean, who)
            return None
        new_cid = _to_int(row.get("character_id"))
        self.logger.info("[建档] 允许创建 %s（id=%s，依据=%s，来源=%s）",
                         clean, new_cid, src, who)
        return new_cid

    def resolve_id(self, ref: Any) -> Optional[int]:
        """把 id / 名字 / 别名解析成 character_id；找不到返回 None。"""
        cid = _to_int(ref)
        if cid is not None:
            row = self.db.query_one(
                "SELECT character_id FROM characters WHERE character_id = ?", (cid,))
            return int(row["character_id"]) if row else None

        target = _bounded_str(ref, NAME_MAX_LEN)
        if not target:
            return None

        row = self.db.query_one(
            "SELECT character_id FROM characters WHERE name = ?", (target,))
        if row:
            return int(row["character_id"])

        for r in self.db.query("SELECT character_id, aliases FROM characters"):
            for alias in _as_list(r.get("aliases")):
                if str(alias).strip() == target:
                    return int(r["character_id"])
        return None

    def resolve_name(self, ref: Any) -> Optional[str]:
        """把 id / 名字解析成规范名字。"""
        cid = self.resolve_id(ref)
        if cid is None:
            return None
        row = self._fetch_by_id(cid)
        return str(row["name"]) if row else None

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get(self, ref: Any) -> Optional[Dict[str, Any]]:
        """按 id / 名字 / 别名取角色。"""
        return self._fetch_by_id(self.resolve_id(ref))

    def all(
        self,
        role_type: Optional[str] = None,
        active_only: bool = False,
        include_purged: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出全部角色，核心角色优先、发言多的优先。

        [V2.7] 默认**排除已「彻底移除」**的角色（``purged_at`` 非空）——
        彻底移除 = 从所有 UI 列表消失。``include_purged=True`` 才连它们一起返回。
        """
        sql = ("SELECT * FROM characters WHERE purged_at IS NULL"
               if not include_purged else "SELECT * FROM characters WHERE 1 = 1")
        params: List[Any] = []
        if role_type is not None:
            sql += " AND role_type = ?"
            params.append(self._validate_role_type(role_type))
        if active_only:
            sql += " AND active = 1"
        sql += (" ORDER BY CASE role_type WHEN 'user' THEN 4 "
                "WHEN 'main_character' THEN 3 WHEN 'npc' THEN 2 "
                "WHEN 'system' THEN 1 ELSE 0 END DESC, "
                "message_count DESC, character_id ASC")
        return self.db.query(sql, tuple(params))

    def get_user(self) -> Optional[Dict[str, Any]]:
        """取 ``is_user = 1`` 的角色（人类玩家）。"""
        row = self.db.query_one(
            "SELECT * FROM characters WHERE is_user = 1 "
            "ORDER BY message_count DESC, character_id ASC LIMIT 1")
        if row:
            return row
        return self.db.query_one(
            "SELECT * FROM characters WHERE role_type = ? "
            "ORDER BY message_count DESC, character_id ASC LIMIT 1", (ROLE_USER,))

    def count(self) -> int:
        """角色总数。"""
        return self.db.count("characters")

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------
    def increment_message_count(self, ref: Any, delta: int = 1) -> int:
        """发言计数 +delta 并刷新 last_seen；返回新的计数（失败返回 0）。"""
        cid = self.resolve_id(ref)
        if cid is None:
            return 0
        now = now_iso()
        cur = self.db.execute(
            "UPDATE characters SET message_count = message_count + ?, "
            "last_seen = ? WHERE character_id = ?",
            (int(delta), now, cid))
        if cur is None:
            return 0
        return int(self.db.scalar(
            "SELECT message_count FROM characters WHERE character_id = ?",
            (cid,), 0) or 0)

    def set_role(self, ref: Any, role_type: str) -> bool:
        """设置 role_type。"""
        cid = self.resolve_id(ref)
        if cid is None:
            self.logger.warning("[角色] set_role 失败：%r 不存在", ref)
            return False
        rt = self._validate_role_type(role_type)
        cur = self.db.execute(
            "UPDATE characters SET role_type = ? WHERE character_id = ?",
            (rt, cid))
        if cur is not None:
            self.logger.info("[角色] %s 身份置为 %s", cid, rt)
        return cur is not None

    def set_static_profile(self, ref: Any, profile: Dict[str, Any]) -> bool:
        """设置 static_profile（角色卡固定设定）。"""
        cid = self.resolve_id(ref)
        if cid is None:
            return False
        cur = self.db.execute(
            "UPDATE characters SET static_profile = ? WHERE character_id = ?",
            (_json_dumps(_as_dict(profile)), cid))
        return cur is not None

    def set_profile(self, ref: Any, profile: Dict[str, Any]) -> bool:
        """设置 profile（动态人物档案）。"""
        cid = self.resolve_id(ref)
        if cid is None:
            return False
        cur = self.db.execute(
            "UPDATE characters SET profile = ? WHERE character_id = ?",
            (_json_dumps(_as_dict(profile)), cid))
        return cur is not None

    def set_traits(
        self,
        ref: Any,
        traits: Union[Sequence[Any], str],
        merge: bool = True,
    ) -> bool:
        """写入 traits。

        ``merge=True`` 时与已有值合并去重；``False`` 时整体替换。
        """
        cid = self.resolve_id(ref)
        if cid is None:
            return False
        incoming = [str(t).strip() for t in _as_list(traits) if str(t).strip()]
        if merge:
            current = self.get_traits(cid)
            for t in incoming:
                if t not in current:
                    current.append(t)
            final = current
        else:
            final = incoming
        cur = self.db.execute(
            "UPDATE characters SET traits = ? WHERE character_id = ?",
            (_json_dumps(final), cid))
        return cur is not None

    def get_traits(self, ref: Any) -> List[str]:
        """读取 traits 列表。"""
        row = self.get(ref)
        return [str(t) for t in _as_list(row.get("traits"))] if row else []

    def set_active(self, ref: Any, active: bool) -> bool:
        """设置 active 标记。"""
        cid = self.resolve_id(ref)
        if cid is None:
            return False
        cur = self.db.execute(
            "UPDATE characters SET active = ? WHERE character_id = ?",
            (1 if active else 0, cid))
        return cur is not None

    # ------------------------------------------------------------------
    # 活跃度 / 晋升
    # ------------------------------------------------------------------
    def auto_detect_active(
        self,
        window_messages: Optional[int] = None,
        window_hours: Optional[float] = None,
    ) -> List[int]:
        """按最近消息窗口刷新 ``active`` 标记，返回活跃角色 id 列表。

        判定：最近 ``window_messages`` 条消息、且发生在 ``window_hours``
        小时以内，有发言记录的角色即为活跃。
        """
        win = int(window_messages or self.memory_cfg.active_window_messages)
        hours = float(window_hours or self.memory_cfg.active_window_hours)
        # [时区一致] 全库时间字段统一北京时间（now_iso 约定），窗口起点也必须
        # 用同一时区渲染 —— 原来传 float 会被 _parse_iso 渲染成 UTC(+00:00)，
        # 与 +08:00 的 send_date 做字符串比较 → 72h 窗口实际变成 80h。
        since = _norm_iso(
            datetime.now(BEIJING_TZ) - timedelta(hours=hours), now_iso())

        rows = self.db.query(
            "SELECT cid, COUNT(*) AS c FROM ("
            "  SELECT character_id AS cid FROM messages "
            "  WHERE character_id IS NOT NULL AND send_date >= ? "
            "  ORDER BY send_date DESC LIMIT ?"
            ") GROUP BY cid ORDER BY c DESC",
            (since, win))
        active_ids = [int(r["cid"]) for r in rows]

        with self.db.transaction():
            # [同卡不隐藏] 只清「散人」（card_id IS NULL）的 active 标记。
            # 卡里的角色永不清 —— 否则这一轮没开口的角色会被标成 inactive，
            # 而 UI 与中继的卡下角色列表都按 active 过滤（list_characters），
            # 结果是角色从卡里凭空消失、且再也选不到当说话人（死循环）。
            self.db.execute("UPDATE characters SET active = 0 "
                            "WHERE active = 1 AND card_id IS NULL "
                            "AND is_user = 0")
            if active_ids:
                marks = ", ".join("?" * len(active_ids))
                self.db.execute(
                    f"UPDATE characters SET active = 1 WHERE character_id IN ({marks})",
                    tuple(active_ids))
        self.logger.info("[角色] 活跃角色 %d 个：%s", len(active_ids), active_ids)
        return active_ids

    def promote_main_candidates(
        self,
        min_messages: Optional[int] = None,
        min_days: Optional[float] = None,
    ) -> List[int]:
        """把够格的 npc / unknown 晋升为 ``main_character``。

        条件（同时满足）：发言数 >= ``min_messages``、
        first_seen 距今 >= ``min_days`` 天。返回被晋升的角色 id 列表。
        """
        mm = int(min_messages if min_messages is not None
                 else self.memory_cfg.main_promote_min_messages)
        md = float(min_days if min_days is not None
                   else self.memory_cfg.main_promote_min_days)
        # [时区一致] 同上：cutoff 原来是 UTC 渲染，与 +08:00 的 first_seen
        # 字符串比较 → 门槛凭空严 8 小时（days=0 实际要满 8 小时）。
        cutoff = _norm_iso(
            datetime.now(BEIJING_TZ) - timedelta(days=md), now_iso())

        rows = self.db.query(
            "SELECT character_id, name, message_count FROM characters "
            "WHERE role_type IN ('npc', 'unknown') AND is_user = 0 "
            "AND message_count >= ? AND (first_seen IS NULL OR first_seen <= ?) "
            "ORDER BY message_count DESC",
            (mm, cutoff))
        ids = [int(r["character_id"]) for r in rows]
        if not ids:
            return []

        marks = ", ".join("?" * len(ids))
        with self.db.transaction():
            self.db.execute(
                f"UPDATE characters SET role_type = ? "
                f"WHERE character_id IN ({marks})",
                tuple([ROLE_MAIN] + ids))
        for r in rows:
            self.logger.info("[角色] 晋升为主角色：%s（id=%s, 发言=%s）",
                             r["name"], r["character_id"], r["message_count"])
        return ids


# ==============================================================================
# V3 追加：CardManager —— 卡片层（作品 / 场景 / 设定集 = characters 的分组容器）
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【07】卡管理
# ══════════════════════════════════════════════════════════════════════

class CardManager:
    """``cards`` 表的管理者（V3 追加）。

    卡片层的作用域边界（V3 铁律，务必牢记）
    ------------------------------------
    * ``cards`` 只是 **characters 的分组容器**，用来把"同一张卡里的角色"
      归到一起，让 UI 能按「卡 → 角色 → 记忆」三级导航。
    * ``memories.owner_character_id`` **永远指向 characters 表**，
      永远不等于 ``card_id``。本类不提供任何写 memories 的方法。
    * 一张卡可以为空（还没有角色）；一个角色最多属于一张卡
      （``attach_character`` 会先把它从旧卡上摘下来）。
    """

    def __init__(
        self,
        db: Database,
        config: Optional[Config] = None,
        char_mgr: Optional["CharacterManager"] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.config = config
        self.char_mgr = char_mgr
        self.logger = logger or _get_logger("cards")

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _resolve_card_id(self, ref: Any) -> Optional[int]:
        """把 card_id / 卡名解析成 card_id；找不到返回 None。"""
        if ref is None or isinstance(ref, bool):
            return None
        cid = _to_int(ref)
        if cid is not None:
            row = self.db.query_one(
                "SELECT card_id FROM cards WHERE card_id = ?", (cid,))
            return int(row["card_id"]) if row else None
        name = _relay_fix_text(ref).strip()
        if not name:
            return None
        row = self.db.query_one(
            "SELECT card_id FROM cards WHERE name = ?", (name,))
        return int(row["card_id"]) if row else None

    def _resolve_char_id(self, ref: Any) -> Optional[int]:
        """把 character_id / 角色名解析成 character_id。"""
        if self.char_mgr is not None:
            try:
                return self.char_mgr.resolve_id(ref)
            except Exception as ex:
                self.logger.warning("[卡片] 解析角色 %r 失败：%s", ref, ex)
                return None
        cid = _to_int(ref)
        return cid

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------
    def resolve_by_alias(self, ref: Any) -> Optional[str]:
        """[V2.3 别名映射] 用别名/关键词反查**真卡名**；命中返回真名，否则 None。

        先比真名（命中即返回自己），再逐行比 ``aliases``（忽略大小写与空白）。
        """
        if ref in (None, "") or isinstance(ref, (int, float)):
            return None
        nm = _relay_fix_text(ref).strip()
        if not nm:
            return None
        try:
            row = self.db.query_one("SELECT name FROM cards WHERE name = ?", (nm,))
            if row:
                return str(row["name"])
            low = nm.lower()
            for r in self.db.query("SELECT name, aliases FROM cards"):
                for a in _as_list(r.get("aliases")):
                    sa = str(a).strip()
                    if sa and sa.lower() == low:
                        return str(r.get("name"))
        except Exception as ex:
            self.logger.warning("[卡片] resolve_by_alias(%r) 失败：%s", ref, ex)
        return None

    def aliases_of(self, card_ref: Any) -> List[str]:
        """[V2.3] 读出卡片别名列表（JSON 列，读出来就是 list）。"""
        cid = self._resolve_card_id(card_ref)
        if cid is None:
            return []
        row = self.db.query_one("SELECT aliases FROM cards WHERE card_id = ?",
                                (cid,))
        return [str(a) for a in _as_list(row.get("aliases"))] if row else []

    def set_aliases(self, card_ref: Any,
                    aliases: Optional[Sequence[Any]] = None,
                    merge: bool = True) -> bool:
        """[V2.3] 写卡片别名（``merge=True`` 与已有值合并去重，上限 ``ALIAS_MAX_COUNT``）。"""
        cid = self._resolve_card_id(card_ref)
        if cid is None:
            return False
        cur_list: List[str] = self.aliases_of(cid) if merge else []
        for a in (aliases or []):
            sa = str(a).strip()
            if sa and sa not in cur_list and len(cur_list) < ALIAS_MAX_COUNT:
                cur_list.append(sa)
        try:
            cur = self.db.execute(
                "UPDATE cards SET aliases = ? WHERE card_id = ?",
                (_json_dumps(cur_list), cid))
            return cur is not None
        except Exception as ex:
            self.logger.warning("[卡片] set_aliases(%r) 失败：%s", card_ref, ex)
            return False

    def get_or_create(self, name: str, source: str = DEFAULT_CARD_SOURCE,
                      aliases: Optional[Sequence[Any]] = None
                      ) -> Optional[int]:
        """取卡 id；不存在则建；已存在则刷新 ``last_seen`` 并合并别名。

        [V2.3 别名映射] 查重顺序是**真名 → 别名**：Tavo 发来「家庭」而库里
        真卡叫「山田家」时，不会再建一张重复卡，而是命中那张卡并补记别名。
        """
        txt = _relay_fix_text(name).strip()
        if not txt:
            return None
        src = str(source or DEFAULT_CARD_SOURCE).strip().lower()
        if src not in VALID_CARD_SOURCES:
            src = DEFAULT_CARD_SOURCE
        try:
            row = self.db.query_one(
                "SELECT card_id FROM cards WHERE name = ?", (txt,))
            if row is None:
                _real = self.resolve_by_alias(txt)      # [V2.3] 别名兜底
                if _real and _real != txt:
                    self.logger.info("[卡片] 别名映射：%s -> %s", txt, _real)
                    row = self.db.query_one(
                        "SELECT card_id FROM cards WHERE name = ?", (_real,))
            now = now_iso()
            if row is not None:
                cid = int(row["card_id"])
                self.db.execute(
                    "UPDATE cards SET last_seen = ? WHERE card_id = ?",
                    (now, cid))
                if aliases:
                    self.set_aliases(cid, aliases, merge=True)
                return cid
            _init_alias = [txt]
            for _a in (aliases or []):
                _sa = str(_a).strip()
                if _sa and _sa not in _init_alias:
                    _init_alias.append(_sa)
            new_id = self.db.insert(
                "INSERT INTO cards (name, source, created_at, last_seen, aliases) "
                "VALUES (?, ?, ?, ?, ?)",
                (txt, src, now, now, _json_dumps(_init_alias)))
            if new_id:
                self.logger.info("[卡片] 新建卡：%s（id=%s, source=%s, 别名=%s）",
                                 txt, new_id, src,
                                 "、".join(_init_alias[1:]) or "无")
            return int(new_id) if new_id else self._resolve_card_id(txt)
        except Exception as ex:
            self.logger.warning("[卡片] get_or_create(%r) 失败：%s", txt, ex)
            return None

    def rename(self, old: str, new: str) -> bool:
        """改卡名；新名已被占用则拒绝。"""
        o = _relay_fix_text(old).strip()
        n = _relay_fix_text(new).strip()
        if not o or not n:
            return False
        oid = self._resolve_card_id(o)
        if oid is None:
            self.logger.warning("[卡片] rename：找不到卡 %r", o)
            return False
        if self._resolve_card_id(n) is not None:
            self.logger.warning("[卡片] rename：卡名已被占用 %r", n)
            return False
        cur = self.db.execute(
            "UPDATE cards SET name = ? WHERE card_id = ?", (n, oid))
        ok = cur is not None and (cur.rowcount or 0) > 0
        if ok:
            self.logger.info("[卡片] 重命名：%s -> %s", o, n)
        return ok

    def attach_character(self, card_ref: Any, char_ref: Any) -> bool:
        """把一个角色挂到卡上；角色已经在别的卡上则先解绑。"""
        card_id = self._resolve_card_id(card_ref)
        ch_id = self._resolve_char_id(char_ref)
        if card_id is None or ch_id is None:
            self.logger.warning("[卡片] attach 失败：卡=%r 角色=%r",
                                card_ref, char_ref)
            return False
        try:
            cur = self.db.execute(
                "UPDATE characters SET card_id = ? WHERE character_id = ?",
                (card_id, ch_id))
            ok = cur is not None and (cur.rowcount or 0) > 0
            if ok:
                self.logger.info("[卡片] 角色 %s 已挂到卡 %s",
                                 char_ref, card_ref)
            return ok
        except Exception as ex:
            self.logger.warning("[卡片] attach 异常：%s", ex)
            return False

    def detach_character(self, char_ref: Any) -> bool:
        """把角色从卡上摘下来（``card_id = NULL``，角色本身不删）。"""
        ch_id = self._resolve_char_id(char_ref)
        if ch_id is None:
            return False
        try:
            cur = self.db.execute(
                "UPDATE characters SET card_id = NULL WHERE character_id = ?",
                (ch_id,))
            ok = cur is not None and (cur.rowcount or 0) > 0
            if ok:
                self.logger.info("[卡片] 角色 %s 已从卡上摘除", char_ref)
            return ok
        except Exception as ex:
            self.logger.warning("[卡片] detach 异常：%s", ex)
            return False

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------
    def get(self, ref: Any) -> Optional[Dict[str, Any]]:
        """按 id / 卡名取一行卡；不存在返回 None。"""
        cid = self._resolve_card_id(ref)
        if cid is None:
            return None
        try:
            return self.db.query_one(
                "SELECT * FROM cards WHERE card_id = ?", (cid,))
        except Exception as ex:
            self.logger.warning("[卡片] get(%r) 失败：%s", ref, ex)
            return None

    def all_names(self) -> List[str]:
        """全部卡名（供中继扫描 system prompt 用）。"""
        try:
            rows = self.db.query(
                "SELECT name FROM cards ORDER BY COALESCE(last_seen, '') DESC")
        except Exception as ex:
            self.logger.warning("[卡片] 读取卡名失败：%s", ex)
            return []
        out: List[str] = []
        for r in rows:
            nm = _relay_fix_text(r.get("name")).strip()
            if nm and nm not in out:
                out.append(nm)
        return out

    def count(self) -> int:
        """卡总数。"""
        try:
            return int(self.db.count("cards"))
        except Exception:
            return 0

    def set_active(self, card_ref: Any, active: bool = True) -> bool:
        """[卡片逻辑删除] 启用 / 逻辑删除一张卡（**只改标记，绝不删行**）。

        ``active=False``（逻辑删除）时，同时把卡下角色「解绑」
        （``characters.card_id`` 置空），它们会落到一级页面的「散装角色」里
        继续可见可点，不会被藏起来；记忆/事件等都不动。

        ``active=True``（恢复）只把标记改回 1，角色保持解绑状态
        （需要重新归卡可用 CLI ``attach-card``）。
        """
        cid = self._resolve_card_id(card_ref)
        if cid is None:
            return False
        flag = 1 if active else 0
        name = ""
        detached = 0
        try:
            row = self.db.query_one(
                "SELECT name FROM cards WHERE card_id = ?", (cid,))
            name = str(row.get("name")) if row else ""
            with self.db.transaction():
                cur = self.db.execute(
                    "UPDATE cards SET is_active = ? WHERE card_id = ?",
                    (flag, cid))
                if cur is None:
                    return False
                if not active:
                    cur2 = self.db.execute(
                        "UPDATE characters SET card_id = NULL "
                        "WHERE card_id = ?", (cid,))
                    detached = int(cur2.rowcount) if cur2 is not None else 0
            self.logger.info(
                "[卡片] %s卡：%s（id=%s，解绑角色=%s）—— 未删除任何数据行",
                "恢复" if active else "逻辑删除", name, cid, detached)
            return True
        except Exception as ex:
            self.logger.warning("[卡片] set_active(%r, %s) 失败：%s",
                                card_ref, active, ex)
            return False

    def list_all(self, include_inactive: bool = False
                 ) -> List[Dict[str, Any]]:
        """列出全部卡，附带角色数 / 记忆数（UI 一级页面用）。

        ``include_inactive=True`` 时把「逻辑删除」的卡（``is_active=0``）
        也一起返回（附带 ``is_active`` 字段），供 UI 的「恢复」区使用。
        """
        where = "" if include_inactive else "WHERE COALESCE(c.is_active, 1) = 1 "
        sql = (
            "SELECT c.card_id, c.name, c.source, c.cover, "
            "       c.created_at, c.last_seen, c.is_active, "
            "  (SELECT COUNT(*) FROM characters ch "
            "     WHERE ch.card_id = c.card_id) AS character_count, "
            "  (SELECT COUNT(*) FROM memories m "
            "     WHERE m.owner_character_id IN "
            "           (SELECT ch2.character_id FROM characters ch2 "
            "              WHERE ch2.card_id = c.card_id)) AS memory_count "
            "FROM cards c "
            + where +
            "ORDER BY COALESCE(c.last_seen, '') DESC, c.card_id ASC")
        try:
            rows = self.db.query(sql)
        except Exception as ex:
            self.logger.warning("[卡片] list_all 失败：%s", ex)
            return []
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "card_id": _to_int(r.get("card_id")),
                "name": r.get("name"),
                "source": r.get("source") or DEFAULT_CARD_SOURCE,
                "cover": r.get("cover") if isinstance(r.get("cover"), dict)
                else {},
                "created_at": r.get("created_at"),
                "last_seen": r.get("last_seen"),
                "character_count": int(r.get("character_count") or 0),
                "memory_count": int(r.get("memory_count") or 0),
                "is_active": 0 if int(r.get("is_active") or 0) == 0 else 1,
            })
        return out

    def list_characters(self, card_ref: Any,
                        include_inactive: bool = False) -> List[Dict[str, Any]]:
        """某张卡下的全部角色（附消息数 / 记忆数），核心角色优先。

        **V2.1**：默认过滤掉 ``active = 0``（已隐藏）的角色。
        """
        card_id = self._resolve_card_id(card_ref)
        if card_id is None:
            return []
        sql = (
            "SELECT ch.character_id, ch.name, ch.role_type, ch.is_user, "
            "       ch.active, ch.message_count, ch.card_id, ch.aliases, "
            "  (SELECT COUNT(*) FROM memories m "
            "     WHERE m.owner_character_id = ch.character_id) AS memory_count, "
            "  (SELECT COUNT(*) FROM beliefs b "
            "     WHERE b.owner_character_id = ch.character_id) AS belief_count, "
            "  (SELECT COUNT(*) FROM knowledge k "
            "     WHERE k.owner_character_id = ch.character_id) "
            "       AS knowledge_count "
            "FROM characters ch WHERE ch.card_id = ? "
            "AND ch.purged_at IS NULL "
            "AND ch.is_user = 0 "          # [用户修复] 用户身份不是卡片角色
            + ("AND ch.active = 1 " if not include_inactive else "")
            + "ORDER BY CASE ch.role_type "
            "           WHEN 'user' THEN 0 WHEN 'main_character' THEN 1 "
            "           WHEN 'npc' THEN 2 WHEN 'system' THEN 3 ELSE 4 END, "
            "         ch.message_count DESC, ch.name ASC")
        try:
            return self.db.query(sql, (card_id,))
        except Exception as ex:
            self.logger.warning("[卡片] list_characters(%r) 失败：%s",
                                card_ref, ex)
            return []

    def loose_characters(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """``card_id IS NULL`` 的"散装角色"（老数据 / 未归卡的角色）。

        **V2.1**：默认只返回 ``active = 1``（被隐藏的角色不再出现在控制台）；
        ``include_inactive=True`` 连隐藏的一起返回，供「已隐藏」区展示和恢复。
        """
        sql = (
            "SELECT ch.character_id, ch.name, ch.role_type, ch.is_user, "
            "       ch.active, ch.message_count, ch.card_id, ch.aliases, "
            "  (SELECT COUNT(*) FROM memories m "
            "     WHERE m.owner_character_id = ch.character_id) AS memory_count, "
            "  (SELECT COUNT(*) FROM beliefs b "
            "     WHERE b.owner_character_id = ch.character_id) AS belief_count, "
            "  (SELECT COUNT(*) FROM knowledge k "
            "     WHERE k.owner_character_id = ch.character_id) "
            "       AS knowledge_count "
            "FROM characters ch WHERE ch.card_id IS NULL "
            "AND ch.purged_at IS NULL "
            + ("AND ch.active = 1 " if not include_inactive else "")
            + "ORDER BY CASE ch.role_type "
            "           WHEN 'user' THEN 0 WHEN 'main_character' THEN 1 "
            "           WHEN 'npc' THEN 2 WHEN 'system' THEN 3 ELSE 4 END, "
            "         ch.message_count DESC, ch.name ASC")
        try:
            return self.db.query(sql)
        except Exception as ex:
            self.logger.warning("[卡片] loose_characters 失败：%s", ex)
            return []

    def adopt_orphan_characters(self, card_ref: Any = None) -> List[Dict[str, Any]]:
        """[V2.2 铁律] 把所有**无卡的真实角色**挂到卡下 —— 严禁散装角色。

        * 只动 ``characters.card_id``（``UPDATE``），**绝不删行**；
        * **用户身份不挂卡**（``is_user = 1`` 或 ``role_type = 'user'``）：
          它是"谁在跟我聊"，不属于任何作品/场景容器，也不参与记忆；
        * ``card_ref`` 为空时挂到兜底卡 ``DEFAULT_CARD_NAME``；
        * 已隐藏（``active = 0``）的角色**同样要挂卡** —— 隐藏只是不出现在列表，
          不代表它可以没有归属。

        返回被归位的角色列表（空列表 = 本来就没有散装角色，零写入）。
        """
        try:
            rows = self.db.query(
                "SELECT character_id, name, active FROM characters "
                "WHERE card_id IS NULL "
                "AND COALESCE(is_user, 0) = 0 "
                "AND COALESCE(role_type, '') <> ?", (ROLE_USER,))
        except Exception as ex:
            self.logger.warning("[卡片] 扫描散装角色失败：%s", ex)
            return []
        if not rows:
            return []
        target = str(card_ref or "").strip() or DEFAULT_CARD_NAME
        card_id = self.get_or_create(target)
        if card_id is None:
            self.logger.warning("[卡片] 兜底卡 %r 创建失败，散装角色仍 %d 个",
                                target, len(rows))
            return []
        done: List[Dict[str, Any]] = []
        for r in rows:
            if self.attach_character(card_id, r.get("character_id")):
                done.append({"character_id": r.get("character_id"),
                             "name": r.get("name"),
                             "active": int(r.get("active") or 0),
                             "card_id": card_id})
        if done:
            self.logger.warning(
                "[卡片] 自动归位 %d 个无卡角色 -> 卡「%s」：%s（只改 card_id，一行没删）",
                len(done), target,
                "、".join(str(d.get("name")) for d in done))
        return done

    def loose_count(self, include_inactive: bool = False) -> int:
        """散装角色数（默认不含被隐藏的）。"""
        try:
            return int(self.db.count(
                "characters",
                "card_id IS NULL" if include_inactive
                else "card_id IS NULL AND active = 1"))
        except Exception:
            return 0

    def card_of_character(self, char_ref: Any) -> Optional[Dict[str, Any]]:
        """反查某角色挂在哪张卡上；没挂卡返回 None。"""
        ch_id = self._resolve_char_id(char_ref)
        if ch_id is None:
            return None
        try:
            row = self.db.query_one(
                "SELECT ch.card_id FROM characters ch "
                "WHERE ch.character_id = ?", (ch_id,))
        except Exception as ex:
            self.logger.warning("[卡片] card_of_character 失败：%s", ex)
            return None
        if not row or _to_int(row.get("card_id")) is None:
            return None
        return self.get(_to_int(row.get("card_id")))

    # ------------------------------------------------------------------
    # [P0] 角色卡设定原文
    # ------------------------------------------------------------------
    def get_persona_text(self, card_ref: Any) -> str:
        """[P0] 取卡的设定原文；没有/取不到返回空串。"""
        row = self.get(card_ref)
        if row is None:
            return ""
        return str(row.get("persona_text") or "")

    def set_persona_text(self, card_ref: Any, text: str) -> bool:
        """[P0] 写入卡的设定原文（中继路径只在为空时调用一次）。"""
        cid = self._resolve_card_id(card_ref)
        if cid is None:
            return False
        val = str(text or "")
        cur = self.db.execute(
            "UPDATE cards SET persona_text = ? WHERE card_id = ?", (val, cid))
        if cur is not None:
            self.logger.info("[卡片] 卡 %s 已落库 persona_text（%d 字）",
                             cid, len(val))
        return cur is not None

    def __repr__(self) -> str:
        return "<CardManager cards=%d loose=%d>" % (self.count(),
                                                    self.loose_count())


# ==============================================================================
# EventManager —— 客观事件
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【08】事件 + 可见性
# ══════════════════════════════════════════════════════════════════════

class EventManager:
    """客观事件与事件链。

    * ``events`` 只存**客观摘要**（``summary``），不带任何角色视角
    * 参与人的"知道程度"存在 ``event_visibility``，由 VisibilityManager 负责；
      本类的 ``add_participant`` 只是一个语义化的转发入口
    * ``event_chain_links`` 把事件串成线索，支持 ``prev_event_id`` 回溯
    """

    def __init__(
        self,
        db: Database,
        config: Optional[Config] = None,
        vis_mgr: Optional["VisibilityManager"] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.config = config
        self.memory_cfg: MemoryConfig = (
            config.memory if config is not None else MemoryConfig()
        )
        self.vis_mgr = vis_mgr
        self.logger = logger or _get_logger("events")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _normalize_event_type(self, event_type: Any) -> str:
        et = str(event_type or DEFAULT_EVENT_TYPE).strip().lower()
        if et not in VALID_EVENT_TYPES:
            self.logger.warning("[事件] 未知 event_type %r，回落为 %s",
                                event_type, DEFAULT_EVENT_TYPE)
            return DEFAULT_EVENT_TYPE
        return et

    @staticmethod
    def _normalize_message_ids(ids: Any) -> List[str]:
        out: List[str] = []
        for mid in _as_list(ids):
            sm = _bounded_str(mid, 128)
            if sm and sm not in out:
                out.append(sm)
            if len(out) >= MAX_SOURCE_MESSAGE_IDS:
                break
        return out

    @staticmethod
    def _dedup_hash(summary: str, occurred_at: Optional[str]) -> str:
        """事件去重指纹：客观摘要 + 发生时间。"""
        return _sha(f"event|{_WS_RE.sub('', summary or '')}|{occurred_at or ''}")

    def _ensure_vis_mgr(self) -> "VisibilityManager":
        """惰性创建 VisibilityManager（避免构造顺序耦合）。"""
        if self.vis_mgr is None:
            self.vis_mgr = VisibilityManager(
                self.db, config=self.config, char_mgr=None, event_mgr=self)
        return self.vis_mgr

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def create_event(
        self,
        summary: str,
        event_type: str = DEFAULT_EVENT_TYPE,
        importance: float = DEFAULT_IMPORTANCE,
        emotional_intensity: float = DEFAULT_EMOTIONAL_INTENSITY,
        occurred_at: Optional[str] = None,
        location: str = "",
        source_message_ids: Optional[Sequence[Any]] = None,
        is_factual: bool = True,
        dedup: bool = True,
        dedup_hash_override: Optional[str] = None,
    ) -> Optional[int]:
        """新建客观事件，返回 event_id（失败返回 None）。

        ``dedup=True`` 时，若已有相同 ``dedup_hash`` 的事件则直接复用其 id
        （不会产生第二条同摘要事件）。
        """
        text = str(summary or "").strip()
        if not text:
            self.logger.warning("[事件] 拒绝新建：summary 为空")
            return None

        et = self._normalize_event_type(event_type)
        occurred = _norm_iso(occurred_at, now_iso())
        msg_ids = self._normalize_message_ids(source_message_ids)
        dh = (str(dedup_hash_override).strip()
              if dedup_hash_override else self._dedup_hash(text, occurred))

        if dedup:
            row = self.db.query_one(
                "SELECT event_id FROM events WHERE dedup_hash = ? LIMIT 1", (dh,))
            if row is not None:
                self.logger.debug("[事件] 命中去重，复用 event_id=%s", row["event_id"])
                return int(row["event_id"])

        event_id = self.db.insert(
            "INSERT INTO events "
            "(summary, event_type, importance, emotional_intensity, occurred_at, "
            " location, source_message_ids, is_factual, dedup_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                text, et,
                _clamp(importance, 0.0, 1.0, DEFAULT_IMPORTANCE),
                _clamp(emotional_intensity, 0.0, 1.0, DEFAULT_EMOTIONAL_INTENSITY),
                occurred, _bounded_str(location, 200),
                _json_dumps(msg_ids), 1 if is_factual else 0, dh, now_iso(),
            ))
        if event_id is None:
            return None
        self.logger.info("[事件] 新建 id=%s type=%s factual=%s summary=%s",
                         event_id, et, bool(is_factual), text[:40])
        return int(event_id)

    def add_participant(
        self,
        event_id: Any,
        character_id: Any,
        role_in_event: Optional[str] = None,
        present: bool = False,
        state: str = VIS_KNOWN,
        partial_content: str = "",
        source: Optional[str] = None,
        source_message_id: Optional[str] = None,
        confidence: float = DEFAULT_VISIBILITY_CONFIDENCE,
        force: bool = False,
    ) -> Optional[int]:
        """登记事件参与人（写入 ``event_visibility``），返回 vis_id。

        实际写库交给 VisibilityManager，以保证状态单调性与"新有效来源"校验
        统一走同一处实现。
        """
        eid = _to_int(event_id)
        cid = _to_int(character_id)
        if eid is None or cid is None:
            self.logger.warning("[事件] add_participant 参数非法：%r / %r",
                                event_id, character_id)
            return None
        return self._ensure_vis_mgr().set_visibility(
            event_id=eid,
            character_id=cid,
            state=state,
            partial_content=partial_content,
            source=source,
            source_message_id=source_message_id,
            confidence=confidence,
            present=present,
            role_in_event=role_in_event,
            force=force,
        )

    def get_event(self, event_id: Any) -> Optional[Dict[str, Any]]:
        """按 id 取事件。"""
        eid = _to_int(event_id)
        if eid is None:
            return None
        return self.db.query_one(
            "SELECT * FROM events WHERE event_id = ?", (eid,))

    def list_events(
        self,
        limit: Optional[int] = None,
        factual_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出事件（新 -> 旧）。"""
        sql = "SELECT * FROM events WHERE 1 = 1"
        params: List[Any] = []
        if factual_only:
            sql += " AND is_factual = 1"
        sql += " ORDER BY occurred_at DESC, event_id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def count(self) -> int:
        """事件总数。"""
        return self.db.count("events")

    # ------------------------------------------------------------------
    # 事件链
    # ------------------------------------------------------------------
    def get_or_create_chain(
        self,
        name: str,
        description: str = "",
    ) -> Optional[int]:
        """按名字取事件链，不存在则创建；返回 chain_id。"""
        clean = _bounded_str(name, 128)
        if not clean:
            self.logger.warning("[事件链] 拒绝：name 为空")
            return None
        row = self.db.query_one(
            "SELECT chain_id, description FROM event_chains WHERE name = ?", (clean,))
        if row is not None:
            if description and description != (row.get("description") or ""):
                self.db.execute(
                    "UPDATE event_chains SET description = ? WHERE chain_id = ?",
                    (_bounded_str(description, 500), int(row["chain_id"])))
            return int(row["chain_id"])

        chain_id = self.db.insert(
            "INSERT INTO event_chains(name, description, created_at) VALUES(?, ?, ?)",
            (clean, _bounded_str(description, 500), now_iso()))
        if chain_id is None:
            row = self.db.query_one(
                "SELECT chain_id FROM event_chains WHERE name = ?", (clean,))
            return int(row["chain_id"]) if row else None
        self.logger.info("[事件链] 新建 id=%s name=%s", chain_id, clean)
        return int(chain_id)

    def link_event_to_chain(
        self,
        chain_id: Any,
        event_id: Any,
        sequence: Optional[int] = None,
        prev_event_id: Optional[int] = None,
    ) -> bool:
        """把事件挂到事件链上（重复挂载同一链是安全的）。

        ``sequence`` 为空时自动取"当前链内最大序号 + 1"。
        """
        cid = _to_int(chain_id)
        eid = _to_int(event_id)
        if cid is None or eid is None:
            self.logger.warning("[事件链] link 参数非法：%r / %r", chain_id, event_id)
            return False

        if self.db.query_one(
                "SELECT chain_id FROM event_chains WHERE chain_id = ?", (cid,)) is None:
            self.logger.warning("[事件链] 挂载失败：链 %s 不存在", cid)
            return False
        if self.db.query_one(
                "SELECT event_id FROM events WHERE event_id = ?", (eid,)) is None:
            self.logger.warning("[事件链] 挂载失败：事件 %s 不存在", eid)
            return False

        if sequence is None:
            existing = self.db.query_one(
                "SELECT link_id FROM event_chain_links "
                "WHERE chain_id = ? AND event_id = ?", (cid, eid))
            if existing is not None:
                return True
            max_seq = self.db.scalar(
                "SELECT COALESCE(MAX(sequence), 0) FROM event_chain_links "
                "WHERE chain_id = ?", (cid,), 0)
            sequence = int(max_seq or 0) + 1

        prev = _to_int(prev_event_id)
        if prev is None:
            prev = self.db.scalar(
                "SELECT event_id FROM event_chain_links WHERE chain_id = ? "
                "ORDER BY sequence DESC, link_id DESC LIMIT 1", (cid,), None)
            prev = _to_int(prev)

        cur = self.db.execute(
            "INSERT INTO event_chain_links(chain_id, event_id, sequence, prev_event_id) "
            "VALUES(?, ?, ?, ?) "
            "ON CONFLICT(chain_id, event_id) DO UPDATE SET "
            "sequence = excluded.sequence, prev_event_id = excluded.prev_event_id",
            (cid, eid, int(sequence), prev))
        if cur is not None:
            self.logger.debug("[事件链] 事件 %s -> 链 %s（seq=%s）", eid, cid, sequence)
        return cur is not None

    def chain_history(
        self,
        chain_id: Any,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """按序回放整条事件链（含每个事件的参与人可见性概览）。"""
        cid = _to_int(chain_id)
        if cid is None:
            return []
        sql = (
            "SELECT l.link_id, l.chain_id, l.event_id, l.sequence, l.prev_event_id, "
            "       e.summary, e.event_type, e.importance, e.emotional_intensity, "
            "       e.occurred_at, e.location, e.is_factual, e.source_message_ids "
            "FROM event_chain_links l "
            "JOIN events e ON e.event_id = l.event_id "
            "WHERE l.chain_id = ? "
            "ORDER BY l.sequence ASC, l.link_id ASC"
        )
        params: List[Any] = [cid]
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = self.db.query(sql, tuple(params))

        if rows:
            eids = [int(r["event_id"]) for r in rows]
            marks = ", ".join("?" * len(eids))
            vis_rows = self.db.query(
                f"SELECT event_id, character_id, state, present, role_in_event, "
                f"       source FROM event_visibility WHERE event_id IN ({marks})",
                tuple(eids))
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for v in vis_rows:
                grouped.setdefault(int(v["event_id"]), []).append(v)
            for r in rows:
                r["participants"] = grouped.get(int(r["event_id"]), [])
        return rows

    def get_chain(self, chain_id: Any) -> Optional[Dict[str, Any]]:
        """按 id 取事件链。"""
        cid = _to_int(chain_id)
        if cid is None:
            return None
        return self.db.query_one(
            "SELECT * FROM event_chains WHERE chain_id = ?", (cid,))

    def list_chains(self) -> List[Dict[str, Any]]:
        """列出全部事件链（附事件数）。"""
        return self.db.query(
            "SELECT c.*, (SELECT COUNT(*) FROM event_chain_links l "
            "             WHERE l.chain_id = c.chain_id) AS event_count "
            "FROM event_chains c ORDER BY c.chain_id ASC")


# ==============================================================================
# VisibilityManager —— 事件可见性（状态单调性 + 新有效来源校验）
# ==============================================================================

class VisibilityManager:
    """``event_visibility`` 的唯一写入入口，完整实现 SPEC 强制校验 13。

    优先级：``RUMORED(1) < SUSPECTED(2) < KNOWN(3)``

    分支判断（old = 库中现有记录，new = 本次 proposal）::

        a) old 不存在            -> 首次写入（需通过 state / partial_content 校验）
        b) old.state == new.state-> 同级更新：只改
                                    partial_content / confidence / source /
                                    source_message_ids / updated_at
                                    不改 state / present / role_in_event
        c) old 优先级 < new       -> 升级：必须伴随"新有效来源"，四者满足其一
                                     新 source_message_id / 新 source /
                                     不同 event_id / force=True
        d) old 优先级 > new       -> 降级：一律拒绝

    返回值约定
    ----------
    * 成功           -> ``vis_id`` (int)
    * 被策略拒绝     -> ``None``（降级 / 无新来源 / partial_content 缺失 /
                        事件或角色不存在 / state=UNKNOWN）
    * 调用方参数非法 -> ``ValueError``（state、role_in_event 不在枚举内 —— 这类
                        属于程序错误，不该被静默吞掉）

    关于"不同 event_id"
    -------------------
    本表以 ``(event_id, character_id)`` 为唯一键，"proposal 关联了一个不同的
    event_id"无法指本条记录自身的 event_id。因此实现为：可选尾参
    ``evidence_event_id`` 表示**提供证据的另一个事件**；它等于本行 event_id 时
    不算新来源，不同则构成升级理由。不传则该项不成立。
    """

    def __init__(
        self,
        db: Database,
        config: Optional[Config] = None,
        char_mgr: Optional[CharacterManager] = None,
        event_mgr: Optional[EventManager] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.config = config
        self.char_mgr = char_mgr
        self.event_mgr = event_mgr
        self.logger = logger or _get_logger("visibility")

    # ==================================================================
    # 内部工具
    # ==================================================================
    @staticmethod
    def rank(state: Any) -> int:
        """状态 -> 优先级数字；未知状态返回 0。"""
        return VISIBILITY_RANK.get(str(state or "").strip().upper(), 0)

    @staticmethod
    def needs_partial(state: Any) -> bool:
        """该状态是否强制要求非空 partial_content。"""
        return str(state or "").strip().upper() in VISIBILITY_NEEDS_PARTIAL

    @staticmethod
    def _validate_state(state: Any) -> str:
        st = str(state or "").strip().upper()
        if st not in VALID_VISIBILITY_STATES:
            raise ValueError(
                f"非法 event_visibility.state：{state!r}，"
                f"应为 {VALID_VISIBILITY_STATES} 之一（注意：没有 UNKNOWN）")
        return st

    @staticmethod
    def _validate_role_in_event(role_in_event: Any) -> Optional[str]:
        """role_in_event 允许为空；非空则必须在枚举内。"""
        if role_in_event is None or str(role_in_event).strip() == "":
            return None
        rv = str(role_in_event).strip().lower()
        if rv not in ROLE_IN_EVENT_VALUES:
            raise ValueError(
                f"非法 role_in_event：{role_in_event!r}，"
                f"应为 {ROLE_IN_EVENT_VALUES} 之一或 None")
        return rv

    @staticmethod
    def _validate_source(source: Any) -> Optional[str]:
        """source 允许为空；非空则必须是固定取值或 ``heard_from:<name>``。"""
        if source is None or str(source).strip() == "":
            return None
        src = _bounded_str(source, MAX_SOURCE_LEN)
        if not src:
            return None
        low = src.lower()
        if low in FIXED_VISIBILITY_SOURCES:
            return low
        if low.startswith(SOURCE_HEARD_FROM_PREFIX):
            who = src[len(SOURCE_HEARD_FROM_PREFIX):].strip()
            if who:
                return SOURCE_HEARD_FROM_PREFIX + who
        # 宽容：其它自由来源只告警不拒绝（heard_from 之外的扩展写法）
        return src

    @staticmethod
    def _append_message_id(
        ids: Any,
        message_id: Optional[str],
        cap: int = MAX_SOURCE_MESSAGE_IDS,
    ) -> List[str]:
        """把本次 source_message_id 追加进 source_message_ids（幂等、保序）。"""
        out = [str(x) for x in _as_list(ids)]
        if message_id:
            sm = str(message_id)
            if sm not in out:
                out.append(sm)
        if len(out) > cap:
            out = out[-cap:]
        return out

    def _event_exists(self, event_id: int) -> bool:
        return self.db.query_one(
            "SELECT event_id FROM events WHERE event_id = ?", (int(event_id),)) is not None

    def _character_exists(self, character_id: int) -> bool:
        return self.db.query_one(
            "SELECT character_id FROM characters WHERE character_id = ?",
            (int(character_id),)) is not None

    def _has_new_evidence(
        self,
        row: Dict[str, Any],
        source: Optional[str],
        source_message_id: Optional[str],
        event_id: int,
        evidence_event_id: Optional[int],
        force: bool,
    ) -> Tuple[bool, str]:
        """判定升级是否伴随"新有效来源"，返回 (是否通过, 依据标签)。"""
        if force:
            return True, "force"

        known_ids = [str(x) for x in _as_list(row.get("source_message_ids"))]
        if source_message_id and str(source_message_id) not in known_ids:
            return True, "new_source_message_id"

        if source and source != str(row.get("source") or ""):
            return True, "new_source"

        ev = _to_int(evidence_event_id)
        if ev is not None and ev != int(event_id):
            return True, "different_event_id"

        return False, ""

    # ==================================================================
    # 写入（唯一入口）
    # ==================================================================
    def set_visibility(
        self,
        event_id: Any,
        character_id: Any,
        state: str,
        partial_content: Optional[str] = None,
        source: Optional[str] = None,
        source_message_id: Optional[str] = None,
        confidence: float = DEFAULT_VISIBILITY_CONFIDENCE,
        present: bool = False,
        role_in_event: Optional[str] = None,
        force: bool = False,
        evidence_event_id: Optional[int] = None,
    ) -> Optional[int]:
        """写入 / 更新一条可见性记录，返回 ``vis_id``；被策略拒绝返回 ``None``。

        校验顺序：
          1. id 可转 int；事件与角色都存在
          2. state ∈ {KNOWN, SUSPECTED, RUMORED}（UNKNOWN 直接拒绝，不落库）
          3. SUSPECTED / RUMORED 必须带非空 partial_content
          4. 首次写入 -> INSERT
          5. 降级 -> 拒绝
          6. 同级 -> 只更新内容字段
          7. 升级 -> 必须有新有效来源
          8. 任何写入/更新后把 source_message_id 追加进 source_message_ids
        """
        if isinstance(event_id, bool) or isinstance(character_id, bool):
            self.logger.warning("[可见性] 拒绝：event_id / character_id 不接受布尔值")
            return None
        eid = _to_int(event_id)
        cid = _to_int(character_id)
        if eid is None or cid is None:
            self.logger.warning("[可见性] 拒绝：id 非法 %r / %r", event_id, character_id)
            return None

        # ---- state：UNKNOWN 是"不落库"的语义值，单独拦掉 ----
        raw_state = str(state or "").strip().upper()
        if raw_state == "UNKNOWN":
            self.logger.warning(
                "[可见性] 拒绝：UNKNOWN 不落库（事件 %s / 角色 %s）—— "
                "完全不知道就应当不写记录", eid, cid)
            return None
        new_state = self._validate_state(raw_state)

        # ---- partial_content 强制校验 ----
        partial = str(partial_content or "").strip()
        if new_state in VISIBILITY_NEEDS_PARTIAL and not partial:
            self.logger.warning(
                "[可见性] 拒绝：state=%s 必须携带非空 partial_content"
                "（事件 %s / 角色 %s）", new_state, eid, cid)
            return None

        src = self._validate_source(source)
        role = self._validate_role_in_event(role_in_event)
        msg_id = _bounded_str(source_message_id, 128) or None
        conf = _clamp(confidence, 0.0, 1.0, DEFAULT_VISIBILITY_CONFIDENCE)
        pres = 1 if present else 0
        ev_evidence = _to_int(evidence_event_id)
        now = now_iso()

        if not self._event_exists(eid):
            self.logger.warning("[可见性] 拒绝：事件 %s 不存在", eid)
            return None
        if not self._character_exists(cid):
            self.logger.warning("[可见性] 拒绝：角色 %s 不存在", cid)
            return None

        old = self.get_visibility(eid, cid)

        # ================= a) 首次写入 =================
        if old is None:
            initial_ids = self._append_message_id([], msg_id)
            vis_id = self.db.insert(
                "INSERT INTO event_visibility "
                "(event_id, character_id, present, role_in_event, state, "
                " partial_content, confidence, source, source_message_ids, "
                " learned_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, cid, pres, role, new_state, partial or None, conf, src,
                 _json_dumps(initial_ids), now, now))
            if vis_id is None:
                return None
            self.logger.info(
                "[可见性] 新建 事件=%s 角色=%s state=%s present=%s 证据=%s",
                eid, cid, new_state, bool(present), initial_ids or "-")
            return int(vis_id)

        # ================= 已有记录 =================
        vis_id = int(old["vis_id"])
        old_state = str(old.get("state") or "").strip().upper()
        old_rank = self.rank(old_state)
        new_rank = VISIBILITY_RANK[new_state]
        old_ids = _as_list(old.get("source_message_ids"))

        # ---- d) 降级：一律拒绝 ----
        if new_rank < old_rank:
            self.logger.warning(
                "[可见性] 拒绝降级：事件 %s 角色 %s %s(%d) -> %s(%d)",
                eid, cid, old_state, old_rank, new_state, new_rank)
            return None

        # ---- b) 同级：只更新内容字段 ----
        if new_rank == old_rank:
            merged_ids = self._append_message_id(old_ids, msg_id)
            cur = self.db.execute(
                "UPDATE event_visibility SET "
                " partial_content = ?, confidence = ?, source = ?, "
                " source_message_ids = ?, updated_at = ? "
                "WHERE vis_id = ?",
                (partial or None, conf, src if src is not None else old.get("source"),
                 _json_dumps(merged_ids), now, vis_id))
            if cur is None:
                return None
            self.logger.debug(
                "[可见性] 同级更新 事件=%s 角色=%s state=%s"
                "（未改 state / present / role_in_event）", eid, cid, old_state)
            return vis_id

        # ---- c) 升级：必须有新有效来源 ----
        has_evidence, reason = self._has_new_evidence(
            old, src, msg_id, eid, ev_evidence, force)
        if not has_evidence:
            self.logger.warning(
                "[可见性] 拒绝升级：事件 %s 角色 %s %s -> %s，但未伴随新有效来源"
                "（需 新 source_message_id / 新 source / 不同 event_id / force=True）",
                eid, cid, old_state, new_state)
            return None

        merged_ids = self._append_message_id(old_ids, msg_id)
        cur = self.db.execute(
            "UPDATE event_visibility SET "
            " state = ?, partial_content = ?, confidence = ?, source = ?, "
            " source_message_ids = ?, updated_at = ? "
            "WHERE vis_id = ?",
            (new_state, partial or None, conf,
             src if src is not None else old.get("source"),
             _json_dumps(merged_ids), now, vis_id))
        if cur is None:
            return None
        self.logger.info(
            "[可见性] 升级 事件=%s 角色=%s %s(%d) -> %s(%d)，依据=%s，证据数=%d",
            eid, cid, old_state, old_rank, new_state, new_rank,
            reason, len(merged_ids))
        return vis_id

    # ==================================================================
    # 读取
    # ==================================================================
    def get_visibility(
        self,
        event_id: Any,
        character_id: Any,
    ) -> Optional[Dict[str, Any]]:
        """取一条可见性记录；不存在返回 None（**没有任何记录 = 完全不知道**）。"""
        if isinstance(event_id, bool) or isinstance(character_id, bool):
            return None
        eid = _to_int(event_id)
        cid = _to_int(character_id)
        if eid is None or cid is None:
            return None
        return self.db.query_one(
            "SELECT * FROM event_visibility WHERE event_id = ? AND character_id = ?",
            (eid, cid))

    def state_of(self, event_id: Any, character_id: Any) -> Optional[str]:
        """只取状态字符串；未记录返回 None。"""
        row = self.get_visibility(event_id, character_id)
        return str(row["state"]) if row else None

    def list_for_character(
        self,
        character_id: Any,
        state: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """某角色"知道/怀疑/听说"的全部事件（带事件摘要），按发生时间倒序。"""
        cid = _to_int(character_id)
        if cid is None:
            return []
        sql = (
            "SELECT v.*, e.summary AS event_summary, e.event_type, "
            "       e.occurred_at, e.location, e.importance, e.is_factual "
            "FROM event_visibility v "
            "JOIN events e ON e.event_id = v.event_id "
            "WHERE v.character_id = ?"
        )
        params: List[Any] = [cid]
        if state is not None:
            params_state = self._validate_state(state)
            sql += " AND v.state = ?"
            params.append(params_state)
        sql += " ORDER BY e.occurred_at DESC, v.vis_id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def list_for_event(
        self,
        event_id: Any,
        state: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """某事件在各角色处的可见情况，KNOWN 优先。"""
        eid = _to_int(event_id)
        if eid is None:
            return []
        sql = (
            "SELECT v.*, c.name AS character_name, c.role_type "
            "FROM event_visibility v "
            "JOIN characters c ON c.character_id = v.character_id "
            "WHERE v.event_id = ?"
        )
        params: List[Any] = [eid]
        if state is not None:
            params_state = self._validate_state(state)
            sql += " AND v.state = ?"
            params.append(params_state)
        sql += (" ORDER BY CASE v.state WHEN 'KNOWN' THEN 3 "
                "WHEN 'SUSPECTED' THEN 2 ELSE 1 END DESC, v.vis_id ASC")
        return self.db.query(sql, tuple(params))

    def count_for_event(self, event_id: Any) -> int:
        """某事件已登记可见性的角色数。"""
        eid = _to_int(event_id)
        if eid is None:
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM event_visibility WHERE event_id = ?",
            (eid,), 0) or 0)

    # ==================================================================
    # 便捷判定
    # ==================================================================
    def knows(self, event_id: Any, character_id: Any) -> bool:
        """角色是否处于 KNOWN（明确知情）。"""
        return self.state_of(event_id, character_id) == VIS_KNOWN

    def suspects(self, event_id: Any, character_id: Any) -> bool:
        """角色是否至少处于 SUSPECTED（察觉及以上）。"""
        return self.rank(self.state_of(event_id, character_id)) >= \
            VISIBILITY_RANK[VIS_SUSPECTED]

    def has_heard(self, event_id: Any, character_id: Any) -> bool:
        """角色是否至少听过风声（有任何非空记录）。"""
        return self.rank(self.state_of(event_id, character_id)) >= \
            VISIBILITY_RANK[VIS_RUMORED]

    def __repr__(self) -> str:
        return f"<VisibilityManager db={self.db!r}>"


# ==============================================================================
# 第 2 批：记忆层 —— MemoryManager / KnowledgeManager /
#          BeliefManager / AssociationManager
# ==============================================================================

# ---------- 批 2 补充常量 ----------
#: 可被检索到的记忆状态（superseded / contradicted / archived 不再进入上下文）
RETRIEVABLE_MEMORY_STATUSES: Tuple[str, ...] = (
    MEM_STATUS_ACTIVE, MEM_STATUS_REINFORCED, MEM_STATUS_WEAKENED,
    MEM_STATUS_CONSOLIDATED,
)
MEM_CONTENT_MAX_LEN = 4000

#: 冲突检测：否定词（出现即认为极性相反）
NEGATION_MARKERS: Tuple[str, ...] = (
    "不", "没", "别", "无", "未", "非", "拒绝", "否认", "从不", "绝不",
    "not ", "never", "no ", "didn't", "don't", "doesn't", "cannot",
)
#: 冲突检测：反义对（命中任一即认为极性相反）
ANTONYM_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("喜欢", "讨厌"), ("爱", "恨"), ("信任", "怀疑"), ("亲近", "疏远"),
    ("答应", "拒绝"), ("友好", "敌意"), ("帮助", "伤害"), ("真", "假"),
    ("安全", "危险"), ("活着", "死了"), ("朋友", "敌人"),
)
CONFLICT_SIMILARITY_THRESHOLD = 0.60
CONFLICT_MAX_PAIRS_PER_RUN = 200
CONFLICT_STATUS_OPEN = "open"

#: 记忆关联
ASSOC_DEFAULT_TYPE = "related"
ASSOC_AUTO_LINK_THRESHOLD = 0.45
ASSOC_MAX_AUTO_LINKS = 8


# ==============================================================================
# 10. MemoryManager —— 记忆写入 / 检索 / 衰减 / 冲突 / 压缩
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【09】记忆管理（核心）
# ══════════════════════════════════════════════════════════════════════

class MemoryManager:
    """``memories`` 表的管理者。

    铁律（SPEC 原则 11 / 12 与强制校验 4 / 5 / 14）：

    * **记忆永不物理删除**；遗忘 = 降低 ``recall_strength``
    * 重要、情感强烈的记忆衰减更慢
    * ``source_visibility_id`` 非空时 ``owner_character_id`` 必须等于
      该可见性记录的 ``character_id``，否则拒绝写入（防串记忆）
    * 事件型 memory 必须有 ``source_event_id``；事件不存在则**先建事件**
    * 新旧记忆冲突时**绝不覆盖旧记忆**，只写 ``memory_conflicts``
    * consolidation 只吃 ``is_consolidated = 0`` 的原始记忆，摘要不再被压缩
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        vis_mgr: Optional[VisibilityManager] = None,
        event_mgr: Optional[EventManager] = None,
        llm: Optional[Any] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.memory_cfg: MemoryConfig = (
            config.memory if config is not None else MemoryConfig()
        )
        self.vis_mgr = vis_mgr
        self.event_mgr = event_mgr
        #: MemoryExtractor / LLMClient，由 MemoryEngine 在批 5 注入；为 None 时
        #: consolidation 的 llm 模式自动回退 raw
        self.llm = llm
        self.logger = logger or _get_logger("memories")
        #: [IDF/P3] {owner_character_id: (N, MappingProxyType(df))}；惰性构建，发布后只读
        self._df_stats: Dict[int, Any] = {}

    # ==================================================================
    # 内部
    # ==================================================================
    def _resolve_owner(self, owner: Any) -> Optional[int]:
        """owner（id / 名字 / 别名）-> character_id。"""
        if self.char_mgr is None:
            return _to_int(owner)
        return self.char_mgr.resolve_id(owner)

    def _user_names(self) -> Tuple[str, ...]:
        """配置里的「用户名单」（``memory.user_names``），去重去空。"""
        raw: Any = ()
        try:
            raw = getattr(self.memory_cfg, "user_names", ()) or ()
        except Exception:
            raw = ()
        if isinstance(raw, str):
            raw = (raw,)
        out: List[str] = []
        for item in raw:
            txt = str(item or "").strip()
            if txt and txt not in out:
                out.append(txt)
        return tuple(out)

    def _is_user_character(self, cid: Any) -> bool:
        """V3 规则：该角色是不是**用户（人类玩家）**。

        判定依据（命中任一即为用户）：

        1. ``characters.is_user = 1``
        2. 角色名或别名出现在 ``config.memory.user_names`` 里
           （玩家角色真名，比如「明」）

        用户不需要自己的记忆 —— 记忆只服务于 AI 扮演的角色（女主角们）。
        查不到 / 出错一律返回 False（宁可多记，不漏记）。
        """
        oid = _to_int(cid)
        if oid is None:
            return False
        try:
            row = self.db.query_one(
                "SELECT name, aliases, is_user FROM characters "
                "WHERE character_id = ?", (oid,))
            if not row:
                return False
            if row.get("is_user"):
                return True
            wanted = self._user_names()
            if not wanted:
                return False
            cands: List[str] = [str(row.get("name") or "").strip()]
            for a in _as_list(row.get("aliases")):
                cands.append(str(a or "").strip())
            return any(c and c in wanted for c in cands)
        except Exception:
            return False

    @staticmethod
    def _dedup_hash(owner_id: int, memory_type: str, content: str) -> str:
        return _sha(f"mem|{owner_id}|{memory_type}|{_WS_RE.sub('', content or '')}")

    # ==================================================================
    # [V6 阶段B] tier 定级
    # ==================================================================
    @staticmethod
    def _classify_tier(content: Any, memory_type: Any = None,
                       emotional_intensity: Any = None) -> int:
        """把一条记忆定级到 tier 1..4（[V6 阶段B]）。

        * **tier 1** —— 身份 / 核心关系 / **不可逆事件**
        * **tier 4** —— 当前情绪 / 动作 / 场景
        * 其他一律 **tier 3**（默认）

        判定顺序（写明，避免「此刻主人正坐在窗边喝茶」这种混合句含糊）:

        1. ``memory_type ∈ {identity, relationship, secret}`` -> tier 1
        2. 命中 ``TIER1_HARD_KEYWORDS``（不可逆事件：死 / 结婚 / 背叛 …）-> tier 1
        3. 命中 ``TIER4_KEYWORDS``（此刻 / 刚刚 / 正在 / 哭 / 坐下 …）-> tier 4
        4. 命中 ``TIER1_RELATION_KEYWORDS``（我是 / 母亲 / 主人 / 未婚妻 …）-> tier 1
        5. ``memory_type == emotional`` -> tier 4
        6. 其余 -> tier 3

        把「不可逆事件」放在「瞬时场景」之前，是为了让「母亲去世了」永远定级 1；
        而「此刻主人正坐在窗边喝茶」这种**明显带当前时间词**的场景句会先被
        第 3 步接住，定级 4 —— 它描述的是此刻的画面，不是身份。

        纯规则、可复现、**零 token**：只看已落库的文本与类型，不调 LLM。
        """
        text = str(content or "").strip()
        mt = str(memory_type or "").strip().lower()
        if mt in TIER1_MEMORY_TYPES:
            return TIER_CORE
        if any(k in text for k in TIER1_HARD_KEYWORDS):
            return TIER_CORE
        if any(k in text for k in TIER4_KEYWORDS):
            return TIER_TRANSIENT
        if any(k in text for k in TIER1_RELATION_KEYWORDS):
            return TIER_CORE
        if mt == MEM_TYPE_EMOTIONAL:
            return TIER_TRANSIENT
        return DEFAULT_TIER

    def _ensure_event_mgr(self) -> EventManager:
        if self.event_mgr is None:
            self.event_mgr = EventManager(
                self.db, config=self.config, vis_mgr=self.vis_mgr)
        return self.event_mgr

    # ==================================================================
    # 写入
    # ==================================================================
    def add_memory(
        self,
        owner: Any,
        content: str,
        memory_type: str = DEFAULT_MEMORY_TYPE,
        importance: float = DEFAULT_IMPORTANCE,
        confidence: float = DEFAULT_CONFIDENCE,
        emotional_intensity: float = DEFAULT_EMOTIONAL_INTENSITY,
        source_event_id: Optional[int] = None,
        source_message_id: Optional[str] = None,
        source_visibility_id: Optional[int] = None,
        is_subjective: bool = True,
        tags: Optional[Sequence[Any]] = None,
        dedup: bool = True,
        auto_create_event: bool = True,
        status: str = MEM_STATUS_ACTIVE,
        is_consolidated: bool = False,
        consolidated_from: Optional[Sequence[Any]] = None,
        consolidated_mode: Optional[str] = None,
        tier: Optional[int] = None,
        emotional_residue: Optional[float] = None,
        consolidation: Optional[float] = None,
        merged_from: Optional[Sequence[Any]] = None,
        source_type: str = DEFAULT_MEMORY_SOURCE_TYPE,
        story_time: str = "",
    ) -> Optional[int]:
        """写入一条角色私有记忆，返回 ``memory_id``；被校验拦下返回 None。

        校验顺序（与 SPEC 强制校验 4 / 5 对应）：

        1. ``owner`` 必须解析得到 character_id
        2. ``memory_type`` 必须在枚举内
        3. ``source_visibility_id`` 非空 -> 该可见性必须存在，且其
           ``character_id`` 必须等于 owner（**防串记忆**）
        4. ``memory_type`` 属于事件型 -> 必须有可用的 ``source_event_id``；
           缺失且 ``auto_create_event=True`` 时**先创建事件再建记忆**
        5. ``dedup=True`` 且已存在同 owner + 同类型 + 同内容时，直接复用旧
           ``memory_id``（保证重复导入不产生重复记忆）
        """
        cid = self._resolve_owner(owner)
        if cid is None:
            self.logger.warning("[记忆] 拒绝写入：owner %r 无法解析", owner)
            return None

        # ---- V3 规则：**不为 user 角色建记忆** ----
        # 用户（人类玩家）不需要自己的记忆；记忆只服务于 AI 扮演的角色
        # （女主角们）。静默跳过（debug 级日志），不算错误、不写库。
        if self._is_user_character(cid):
            self.logger.debug(
                "[记忆] 跳过：owner %s 是 user 角色（用户不建记忆）", cid)
            return None

        text = str(content or "").strip()
        if not text:
            self.logger.warning("[记忆] 拒绝写入：content 为空（owner=%s）", cid)
            return None
        text = text[:MEM_CONTENT_MAX_LEN]

        mt = str(memory_type or DEFAULT_MEMORY_TYPE).strip().lower()
        if mt not in VALID_MEMORY_TYPES:
            self.logger.warning("[记忆] 拒绝写入：非法 memory_type %r", memory_type)
            return None

        st = str(status or MEM_STATUS_ACTIVE).strip().lower()
        if st not in VALID_MEMORY_STATUSES:
            self.logger.warning("[记忆] 拒绝写入：非法 status %r", status)
            return None

        # ---- 校验 3：source_visibility_id 与 owner 必须一致 ----
        vis_id = _to_int(source_visibility_id)
        if vis_id is not None:
            vis = self.db.query_one(
                "SELECT vis_id, character_id FROM event_visibility WHERE vis_id = ?",
                (vis_id,))
            if vis is None:
                self.logger.warning(
                    "[记忆] 拒绝写入：source_visibility_id=%s 不存在（owner=%s）",
                    vis_id, cid)
                return None
            if int(vis["character_id"]) != int(cid):
                self.logger.warning(
                    "[记忆] 拒绝写入：可见性 %s 属于角色 %s，"
                    "但 owner 是 %s —— 禁止串记忆",
                    vis_id, vis["character_id"], cid)
                return None

        # ---- 校验 5：事件型 memory 必须有 source_event_id ----
        ev_id = _to_int(source_event_id)
        if ev_id is not None:
            if self.db.query_one(
                    "SELECT event_id FROM events WHERE event_id = ?", (ev_id,)) is None:
                self.logger.warning(
                    "[记忆] 拒绝写入：source_event_id=%s 不存在（owner=%s）", ev_id, cid)
                return None
        elif mt in EVENT_BOUND_MEMORY_TYPES:
            if not auto_create_event:
                self.logger.warning(
                    "[记忆] 拒绝写入：memory_type=%s 属事件型，必须带 source_event_id"
                    "（owner=%s）", mt, cid)
                return None
            ev_id = self._ensure_event_mgr().create_event(
                summary=text, event_type=mt, importance=importance,
                emotional_intensity=emotional_intensity,
                occurred_at=now_iso(),
                source_message_ids=[source_message_id] if source_message_id else None)
            if ev_id is None:
                self.logger.warning(
                    "[记忆] 拒绝写入：无法为事件型记忆创建事件（owner=%s, type=%s）",
                    cid, mt)
                return None
            self.logger.info(
                "[记忆] 事件型记忆缺少事件，已先创建 event_id=%s（type=%s）", ev_id, mt)

        dh = self._dedup_hash(cid, mt, text)
        if dedup:
            row = self.db.query_one(
                "SELECT memory_id FROM memories WHERE owner_character_id = ? "
                "AND dedup_hash = ? LIMIT 1", (cid, dh))
            if row is not None:
                self.logger.debug("[记忆] 已存在同内容记忆，复用 memory_id=%s",
                                  row["memory_id"])
                return int(row["memory_id"])

        # ---- 容量保护 ----
        if self.memory_cfg.enforce_capacity:
            total = int(self.db.scalar(
                "SELECT COUNT(*) FROM memories WHERE owner_character_id = ?",
                (cid,), 0) or 0)
            if total >= int(self.memory_cfg.max_memories_per_character):
                self.logger.warning(
                    "[记忆] 角色 %s 记忆数已达上限 %s，拒绝新增（不删除任何旧记忆）",
                    cid, self.memory_cfg.max_memories_per_character)
                return None

        # ---- 来源归一化：非法/未给 -> UNKNOWN（保守默认）----
        _stype = str(source_type or DEFAULT_MEMORY_SOURCE_TYPE).strip().upper()
        if _stype not in VALID_MEMORY_SOURCE_TYPES:
            _stype = DEFAULT_MEMORY_SOURCE_TYPE

        now = now_iso()
        tag_list = [str(t).strip() for t in _as_list(tags) if str(t).strip()]
        cf = [int(x) for x in _as_list(consolidated_from) if _to_int(x) is not None]

        # ---- [V6 阶段B] 生命周期字段取值 ----
        # tier：调用方给了就用，没给就按「身份/核心关系/不可逆事件 -> 1，
        #       当前情绪/动作/场景 -> 4，其他 3」现算一次（纯规则）
        _tier = _to_int(tier)
        if _tier not in VALID_TIERS:
            _tier = self._classify_tier(text, mt, emotional_intensity)
        # emotional_residue：没显式给时用这条记忆的情绪强度当残留初值
        _residue = (emotional_intensity if emotional_residue is None
                    else emotional_residue)
        _er = _clamp(_residue, 0.0, 1.0, 0.0)
        _cons = _clamp(consolidation, 0.0, CONSOLIDATION_MAX,
                       DEFAULT_CONSOLIDATION)
        _mf = [int(x) for x in _as_list(merged_from)
               if _to_int(x) is not None]

        memory_id = self.db.insert(
            "INSERT INTO memories "
            "(owner_character_id, memory_type, content, importance, confidence, "
            " emotional_intensity, recall_strength, created_at, last_recalled, "
            " recall_count, source_event_id, source_message_id, "
            " source_visibility_id, is_subjective, status, is_consolidated, "
            " consolidated_from, consolidated_mode, tags, dedup_hash, "
            " tier, emotional_residue, consolidation, merged_from, "
            " source_type, story_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "        ?, ?, ?, ?, ?, ?)",
            (
                cid, mt, text,
                _clamp(importance, 0.0, 1.0, DEFAULT_IMPORTANCE),
                _clamp(confidence, 0.0, 1.0, DEFAULT_CONFIDENCE),
                _clamp(emotional_intensity, 0.0, 1.0, DEFAULT_EMOTIONAL_INTENSITY),
                DEFAULT_RECALL_STRENGTH, now,
                ev_id, _bounded_str(source_message_id, 128) or None,
                vis_id, 1 if is_subjective else 0, st,
                1 if is_consolidated else 0,
                _json_dumps(cf), consolidated_mode, _json_dumps(tag_list), dh,
                _tier, _er, _cons, _json_dumps(_mf), _stype,
                _bounded_str(story_time, 64) or "",
            ))
        if memory_id is None:
            return None
        self.logger.info(
            "[记忆] 新建 id=%s owner=%s type=%s 重要性=%.2f 主观=%s 事件=%s "
            "可见性=%s tier=%s 情感残留=%.2f 巩固度=%.2f",
            memory_id, cid, mt, _clamp(importance, 0, 1, DEFAULT_IMPORTANCE),
            bool(is_subjective), ev_id, vis_id, _tier, _er, _cons)
        return int(memory_id)

    # ==================================================================
    # 读取
    # ==================================================================
    def get_memory(self, memory_id: Any) -> Optional[Dict[str, Any]]:
        """按 id 取记忆。"""
        mid = _to_int(memory_id)
        if mid is None:
            return None
        return self.db.query_one(
            "SELECT * FROM memories WHERE memory_id = ?", (mid,))

    def list_for(
        self,
        owner: Any,
        limit: Optional[int] = None,
        memory_type: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """列出某角色的记忆（新 -> 旧）。"""
        cid = self._resolve_owner(owner)
        if cid is None:
            return []
        sql = "SELECT * FROM memories WHERE owner_character_id = ?"
        params: List[Any] = [cid]
        if memory_type is not None:
            sql += " AND memory_type = ?"
            params.append(str(memory_type).strip().lower())
        if statuses:
            marks = ", ".join("?" * len(statuses))
            sql += f" AND status IN ({marks})"
            params.extend([str(s).strip().lower() for s in statuses])
        sql += " ORDER BY created_at DESC, memory_id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def count(self, owner: Any = None) -> int:
        """记忆数（owner 为空则统计全库）。"""
        if owner is None:
            return self.db.count("memories")
        cid = self._resolve_owner(owner)
        if cid is None:
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM memories WHERE owner_character_id = ?",
            (cid,), 0) or 0)

    # ==================================================================
    # 检索与打分
    # ==================================================================
    # ==================================================================
    # [IDF/P3] 进程内全量 df 缓存（copy-on-write，无锁）
    # ==================================================================
    def df_cache_snapshot(self) -> Dict[int, Any]:
        """只读一次引用（free-threaded 下走锁）；调用方必须用返回值，勿重复读属性。"""
        if _DF_PUBLISH_LOCK is not None:
            with _DF_PUBLISH_LOCK:
                return self._df_stats
        return self._df_stats          # 单条 LOAD_ATTR，GIL 下原子

    def _df_cache_publish(self, cache: Dict[int, Any]) -> None:
        """发布缓存：**单位是整个 dict，一次赋值，绝不拆成两次写属性。**"""
        if _DF_PUBLISH_LOCK is not None:
            with _DF_PUBLISH_LOCK:
                self._df_stats = cache
        else:
            self._df_stats = cache     # 单条 STORE_ATTR，GIL 下原子

    def build_df_cache(self) -> Dict[int, Any]:
        """全量扫 memories 表，重建 ``{owner: (N, MappingProxy(df))}``。

        * 单次扫描同时算「按 owner」与「全局」两份，超限时退化用后者
        * 每 ``DF_BUILD_CHUNK_ROWS`` 行 ``time.sleep(0.01)`` 让出 GIL，
          避免连续分词阻塞并发的 HTTP 请求
        * 写路径不挂钩子：新写入的记忆其 token 不在 df 里 -> idf 取最大，
          属已知的「新词红利」，由下一轮重建收敛
        """
        per_df: Dict[int, Dict[str, int]] = {}
        per_n: Dict[int, int] = {}
        glob_df: Dict[str, int] = {}
        glob_n = 0
        rows = self.db.query("SELECT owner_character_id, content FROM memories")
        for idx, r in enumerate(rows or [], 1):
            cid = int(r.get("owner_character_id") or 0)
            d = per_df.get(cid)
            if d is None:
                d = per_df[cid] = {}
            for t in _token_set(r.get("content")):
                d[t] = d.get(t, 0) + 1
                glob_df[t] = glob_df.get(t, 0) + 1
            per_n[cid] = per_n.get(cid, 0) + 1
            glob_n += 1
            if idx % DF_BUILD_CHUNK_ROWS == 0:
                time.sleep(0.01)
        est_mb = (sum(len(d) for d in per_df.values())
                  * DF_BYTES_PER_TOKEN / 1024.0 / 1024.0)
        if est_mb > DF_CACHE_MEM_LIMIT_MB:
            cache: Dict[int, Any] = {
                DF_GLOBAL_OWNER: (glob_n, types.MappingProxyType(glob_df))}
            self.logger.warning(
                "[IDF] 按 owner 估算 %.1fMB > 上限 %.0fMB，退化为单份全局 df",
                est_mb, DF_CACHE_MEM_LIMIT_MB)
        else:
            cache = {c: (per_n[c], types.MappingProxyType(d))
                     for c, d in per_df.items()}
        self._df_cache_publish(cache)
        self.logger.info("[IDF] df 缓存已重建：%d 个 owner，估算 %.2fMB，总记忆 %d 条",
                         len(cache), est_mb, glob_n)
        return cache

    def df_stats_for(self, cid: Any):
        """取某 owner 的 ``(N, df)``；缓存为空则**惰性构建**；无该 owner 用全局兜底。"""
        cache = self.df_cache_snapshot()
        if not cache:
            cache = self.build_df_cache()
        try:
            key = int(cid)
        except Exception:
            key = DF_GLOBAL_OWNER
        st = cache.get(key)
        if st is None:
            st = cache.get(DF_GLOBAL_OWNER)
        return st

    def _score(
        self,
        mem: Dict[str, Any],
        query: str = "",
        now: Optional[float] = None,
        stats: Any = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """给单条记忆打分，返回 ``(总分, 明细)``；明细用于 ``--debug``。

        总分 = 相关度·W1 + 记忆强度·W2 + 重要性·W3 + 情绪·0.3 + 新鲜度·0.4
        """
        rel = _relevance(query, mem.get("content"), stats)
        recall_raw = _clamp(mem.get("recall_strength"), 0.0, MEM_RECALL_CEIL,
                            DEFAULT_RECALL_STRENGTH)
        recall = recall_raw / MEM_RECALL_CEIL
        imp = _clamp(mem.get("importance"), 0.0, 1.0, DEFAULT_IMPORTANCE)
        emo = _clamp(mem.get("emotional_intensity"), 0.0, 1.0,
                     DEFAULT_EMOTIONAL_INTENSITY)
        age_days = _hours_since(mem.get("created_at"), now) / 24.0
        fresh = 1.0 / (1.0 + age_days / 30.0)

        total = (RANK_W_RELEVANCE * rel
                 + RANK_W_RECALL * recall
                 + RANK_W_IMPORTANCE * imp
                 + 0.3 * emo
                 + 0.4 * fresh)
        detail = {
            "relevance": round(rel, 4),
            "recall_strength": round(recall_raw, 4),
            "recall_norm": round(recall, 4),
            "importance": round(imp, 4),
            "emotion": round(emo, 4),
            "freshness": round(fresh, 4),
            "age_days": round(age_days, 2),
            "total": round(total, 4),
        }
        return total, detail

    def retrieve(
        self,
        owner: Any,
        query: str = "",
        limit: Optional[int] = None,
        debug: bool = False,
        expand_associations: bool = True,
        statuses: Optional[Sequence[str]] = None,
        touch: bool = False,
    ) -> List[Dict[str, Any]]:
        """检索某角色的记忆，按综合分倒序返回。

        只加载 ``owner`` 自己的记忆（SPEC 原则 8：角色私有记忆不外泄）。
        ``expand_associations=True`` 时，沿 ``associations`` 表带回关联记忆
        （得分打折，标记 ``_from_association``）。
        """
        cid = self._resolve_owner(owner)
        if cid is None:
            return []
        # [V6 阶段C] 高相关唤醒：提问命中 DORMANT 记忆的关键词 -> 先叫醒它，
        #             再走正常检索（否则这一批永远查不到）。
        #             显式传了 statuses 的调用方拥有完全控制权，不做唤醒。
        if statuses is None and bool(getattr(self.memory_cfg,
                                            "dormant_wakeup", True)):
            if str(query or "").strip():
                try:
                    self.wake_dormant(cid, query)
                except Exception as ex:
                    self.logger.warning("[记忆] 唤醒流程异常（跳过）：%s", ex)
        lim = int(limit or self.memory_cfg.retrieve_default_limit)
        # [V6 阶段C] RETRIEVABLE_MEMORY_STATUSES 里**没有** dormant，
        #            所以休眠记忆默认就被过滤掉了（除非刚刚被唤醒）。
        status_list = list(statuses or RETRIEVABLE_MEMORY_STATUSES)
        marks = ", ".join("?" * len(status_list))
        # [修复2] 预筛：SQL 侧只取「强度最高」的前 N 条进入 Python 打分，
        #   避免每次中继都把该角色的全部记忆载入内存（长期运行会拖死手机）。
        #   ORDER BY 命中已有索引 idx_mem_recall(owner_character_id,
        #   recall_strength DESC)；N 同时保证不小于本次请求的 limit，
        #   否则调用方要 200 条却只能拿到 100 条。
        prefetch = max(
            int(getattr(self.memory_cfg, "max_context_memories", 0) or 0) * 3,
            100, lim)
        rows = self.db.query(
            f"SELECT * FROM memories WHERE owner_character_id = ? "
            f"AND status IN ({marks}) "
            f"ORDER BY recall_strength DESC, created_at DESC LIMIT ?",
            tuple([cid] + status_list + [prefetch]))

        now = now_ts()
        # [IDF/P3] 全量 df 缓存（惰性构建）
        stats = self.df_stats_for(cid)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        # [syn] query 同义词扩展：让「规矩」能带出「越界/边界」。
        #       只扩展这里，不动 _relevance 内部、不动 _expand_by_associations。
        query_expanded = _expand_query(query)
        for mem in rows:
            total, detail = self._score(mem, query_expanded, now, stats)
            if total < self.memory_cfg.retrieve_min_score:
                continue
            if debug:
                mem["_score"] = total
                mem["_debug"] = detail
            scored.append((total, mem))

        scored.sort(key=lambda p: (-p[0], -int(p[1].get("memory_id") or 0)))
        picked = [m for _, m in scored[:lim]]

        if expand_associations and picked:
            picked = self._expand_by_associations(picked, cid, debug, now, query,
                                                  stats)

        if touch:
            for mem in picked:
                self._touch_recall(int(mem["memory_id"]))
        return picked

    def _expand_by_associations(
        self,
        picked: List[Dict[str, Any]],
        owner_id: int,
        debug: bool,
        now: Optional[float] = None,
        query: str = "",
        stats: Any = None,
    ) -> List[Dict[str, Any]]:
        """沿关联表补充记忆（最多 ASSOC_EXPAND_LIMIT 条，得分打折）。"""
        seen = {int(m["memory_id"]) for m in picked}
        extra: List[Dict[str, Any]] = []
        ids = list(seen)
        marks = ", ".join("?" * len(ids))
        links = self.db.query(
            f"SELECT memory_a, memory_b, weight FROM associations "
            f"WHERE memory_a IN ({marks}) OR memory_b IN ({marks})",
            tuple(ids + ids))
        for lk in links:
            other = (int(lk["memory_b"]) if int(lk["memory_a"]) in seen
                     else int(lk["memory_a"]))
            if other in seen:
                continue
            row = self.db.query_one(
                "SELECT * FROM memories WHERE memory_id = ? "
                "AND owner_character_id = ?", (other, owner_id))
            if row is None:
                continue
            status = str(row.get("status") or "")
            if status not in RETRIEVABLE_MEMORY_STATUSES:
                continue
            seen.add(other)
            total, detail = self._score(row, query, now, stats)
            total *= ASSOC_EXPAND_DISCOUNT * _clamp(lk.get("weight"), 0.0, 1.0, 1.0)
            row["_from_association"] = True
            if debug:
                row["_score"] = total
                row["_debug"] = detail
            extra.append(row)
            if len(extra) >= ASSOC_EXPAND_LIMIT:
                break
        return picked + extra

    # ==================================================================
    # [V6 阶段C] 休眠唤醒 + 巩固度累加
    # ==================================================================
    def wake_dormant(
        self,
        owner: Any,
        query: str = "",
        max_wake: Optional[int] = None,
    ) -> List[int]:
        """**高相关唤醒**：用户提问命中 DORMANT 记忆的关键词 -> 改回 active。

        [V6 阶段C] 规则：

        * 只在 ``status = 'dormant'`` 的记忆里找（这一批本来**不参与检索**）
        * 匹配用 ``_relevance(query, content)``：问句 token 至少
          ``DORMANT_WAKE_MIN_REL``（0.2，即五分之一）出现在这条记忆里才算命中
        * 命中后：``status -> active``，``recall_strength += DORMANT_WAKE_BOOST``
          （0.2，有 MEM_RECALL_CEIL 上限），并记一次 ``recall_count``
        * 一次最多唤醒 ``DORMANT_WAKE_MAX``（5）条，按相关度倒序
        * **只改 status / strength / 计数**，不新建、不删除任何行

        返回被唤醒的 memory_id 列表（没唤醒就返回空列表）。
        """
        cid = self._resolve_owner(owner)
        q = str(query or "").strip()
        if cid is None or not q:
            return []
        # [修复2-A] 超集预筛：把「哪些内容可能相关」下推到 SQL，避免每轮把
        #   全部休眠记忆读进 Python 再逐条 _tokenize（真正的大头开销）。
        #   正确性：任何能通过 _relevance(q, content) >= DORMANT_WAKE_MIN_REL
        #   的内容，必然字面上包含 q 的至少一个非停用词 token —— 汉字 token
        #   按单字探测、拉丁/数字 token 整词探测，都是**无漏召**的超集，
        #   最终仍由既有的 _relevance 精确判定。
        #   注意**绝不能**用 ORDER BY recall_strength 预筛：休眠记忆强度全挤在
        #   [MEM_RECALL_FLOOR, MEM_DORMANT_THRESHOLD) 这条窄带里，按它排序与
        #   相关度无关，会把真正的命中者直接排除（唤醒退化成抽奖）。
        probes = set()
        for tok in (_token_set(q) - STOP_WORDS):
            if _WORD_RE.fullmatch(tok):
                probes.add(tok)                     # 拉丁/数字：整词探测
            else:
                # 每个 token 只需贡献 1 个字符即可保证无漏召（命中内容
                # 必然完整包含该 token）。优先取非停用词字符：像 bigram
                # 「你还」的『你』本身是停用词，若拿它当探测字符，所有含
                # 『你』的休眠记忆都会涌进候选，筛子等于不存在，随后被
                # LIMIT 截断时真命中者就被丢掉了（已实测复现）。
                # 整个 token 都由停用词构成时（如「我们」）才退回首字符。
                cand = [ch for ch in tok if ch not in STOP_WORDS] or list(tok)
                probes.add(cand[0])
        if not probes:
            # 纯停用词查询：_relevance 对任何内容都返回 0.0，不可能命中。
            return []
        pats = ["%" + p.replace("\\", "\\\\").replace("%", "\\%")
                .replace("_", "\\_") + "%" for p in sorted(probes)]
        clause = " OR ".join(["content LIKE ? ESCAPE '\\'"] * len(pats))
        want = int(max_wake) if max_wake is not None else DORMANT_WAKE_MAX
        # 预筛已把绝大多数休眠记忆挡在外面，这里的 LIMIT 只是防"查询字符
        # 极常见"时的兜底；给足余量，避免把最优命中截掉。
        # DORMANT_WAKE_MAX = 5，其 20 倍 = 100，与硬 floor 100 完全重合，
        # 故三项 max 折叠为两项：100 是硬 floor（当前配置下的实际生效值），
        # want * 2 只在调用方显式传很大的 max_wake（want > 50）时才会超过它。
        sql_limit = max(100, want * 2)
        try:
            rows = self.db.query(
                "SELECT memory_id, content, recall_strength FROM memories "
                "WHERE owner_character_id = ? AND status = ? "
                f"AND ({clause}) LIMIT ?",
                tuple([cid, MEM_STATUS_DORMANT] + pats + [sql_limit]))
        except Exception as ex:
            self.logger.warning("[记忆] 唤醒查询失败（跳过）：%s", ex)
            return []
        # [IDF/P3] 全量 df 缓存（惰性构建）
        stats = self.df_stats_for(cid)
        scored: List[Tuple[float, int, str]] = []
        for r in rows or []:
            rel = _relevance(q, r.get("content"), stats)
            if rel >= DORMANT_WAKE_MIN_REL:
                scored.append((rel, int(r["memory_id"]),
                               str(r.get("content") or "")[:40]))
        if not scored:
            return []
        scored.sort(key=lambda p: (-p[0], -p[1]))
        cap = int(max_wake if max_wake is not None else DORMANT_WAKE_MAX)
        cap = max(1, cap)
        woken: List[int] = []
        now_text = now_iso()
        for rel, mid, snippet in scored[:cap]:
            cur = self.db.execute(
                "UPDATE memories SET status = ?, "
                "recall_strength = MIN(?, recall_strength + ?), "
                "recall_count = recall_count + 1, last_recalled = ? "
                "WHERE memory_id = ? AND status = ?",
                (MEM_STATUS_ACTIVE, MEM_RECALL_CEIL, DORMANT_WAKE_BOOST,
                 now_text, mid, MEM_STATUS_DORMANT))
            if cur is not None and (cur.rowcount or 0) > 0:
                woken.append(mid)
                self.logger.info(
                    "[记忆] 唤醒休眠记忆 id=%s（相关度=%.2f，强度 +%.2f）：%s",
                    mid, rel, DORMANT_WAKE_BOOST, snippet)
        return woken

    def bump_consolidation(
        self,
        memory_ids: Sequence[Any],
        delta: Optional[float] = None,
    ) -> int:
        """[V6 阶段C] 记忆每被**注入一次 Prompt**，``consolidation += 0.05``。

        ``consolidation`` 越高，指数衰减越慢（``1 - BETA * consolidation``
        越小 -> ``lambda_D`` 越小）。上限 ``CONSOLIDATION_MAX``（1.0）。
        返回实际更新的行数。
        """
        ids: List[int] = []
        for x in _as_list(memory_ids):
            v = _to_int(x)
            if v is not None and v not in ids:
                ids.append(v)
        if not ids:
            return 0
        try:
            step = float(delta if delta is not None else CONSOLIDATION_BUMP)
        except Exception:
            step = CONSOLIDATION_BUMP
        marks = ", ".join("?" * len(ids))
        cur = self.db.execute(
            "UPDATE memories SET consolidation = MIN(?, consolidation + ?) "
            "WHERE memory_id IN (%s)" % marks,
            tuple([CONSOLIDATION_MAX, step] + ids))
        if cur is None:
            return 0
        n = int(cur.rowcount or 0)
        if n:
            self.logger.info(
                "[记忆] 巩固度累加：%d 条 +%.2f（被注入上下文）", n, step)
        return n

    def _touch_recall(self, memory_id: int) -> None:
        """记录一次"被想起"（不改 recall_strength，只加计数与时间）。"""
        self.db.execute(
            "UPDATE memories SET recall_count = recall_count + 1, last_recalled = ? "
            "WHERE memory_id = ?", (now_iso(), int(memory_id)))

    # ==================================================================
    # 强化 / 衰减
    # ==================================================================
    def reinforce(
        self,
        memory_id: Any,
        boost: float = MEM_REINFORCE_DEFAULT,
    ) -> bool:
        """强化一条记忆：``recall_strength += boost``，并记录被想起。

        ``status='active'`` 且 boost>0 时顺带升级为 ``'reinforced'``。
        """
        mid = _to_int(memory_id)
        if mid is None:
            return False
        row = self.get_memory(mid)
        if row is None:
            self.logger.warning("[记忆] reinforce 失败：%s 不存在", mid)
            return False
        try:
            delta = float(boost)
        except Exception:
            delta = MEM_REINFORCE_DEFAULT
        new_strength = _clamp(
            float(row.get("recall_strength") or DEFAULT_RECALL_STRENGTH) + delta,
            MEM_RECALL_FLOOR, MEM_RECALL_CEIL, DEFAULT_RECALL_STRENGTH)

        new_status = str(row.get("status") or MEM_STATUS_ACTIVE)
        if new_status == MEM_STATUS_ACTIVE and delta > 0:
            new_status = MEM_STATUS_REINFORCED

        cur = self.db.execute(
            "UPDATE memories SET recall_strength = ?, status = ?, "
            "recall_count = recall_count + 1, last_recalled = ? "
            "WHERE memory_id = ?",
            (new_strength, new_status, now_iso(), mid))
        return cur is not None

    # ==================================================================
    # [V6 阶段B] 指数衰减（废除线性衰减）
    # ==================================================================
    def _interference_set(self) -> set:
        """[V6 阶段B] 干扰度分母：**处于未裁决冲突里**的记忆 id 集合。

        ``interference`` 只取 0.0 / 1.0（有冲突=1.0，衰减加速 GAMMA 倍）。
        **不新增字段** —— 用已有的 ``memory_conflicts`` 表现算，一次查询拿全。
        查询失败按「无干扰」处理（宁可衰减慢一点，不误伤）。
        """
        try:
            rows = self.db.query(
                "SELECT old_memory_id AS mid FROM memory_conflicts "
                "WHERE status = ? "
                "UNION SELECT new_memory_id FROM memory_conflicts "
                "WHERE status = ?", (CONFLICT_STATUS_OPEN, CONFLICT_STATUS_OPEN))
        except Exception as ex:
            self.logger.warning("[记忆] 干扰度查询失败（按 0 处理）：%s", ex)
            return set()
        out = set()
        for r in rows or []:
            mid = _to_int(r.get("mid"))
            if mid is not None:
                out.add(mid)
        return out

    def apply_decay(self, rate: Optional[float] = None) -> int:
        """对所有记忆施加一次**指数**时间衰减，返回被影响的条数。

        [V6 阶段B] 废除线性衰减，改为：

            D(t) = D_0 * exp(-lambda_D * delta_t)
            lambda_D = LAMBDA_BASE * (1 - ALPHA * emotional_residue)
                                   * (1 - BETA  * consolidation)
                                   * (1 + GAMMA * interference)

        取值与锚点
        ----------
        * ``D_0`` = 该行当前的 ``recall_strength``
        * ``delta_t`` = 距**上次结算时间**的天数。结算时间取已有的
          ``last_recalled``（空则回退 ``created_at``）；本函数结算完会把
          ``last_recalled`` 写成当前时刻 —— 该列因此兼作「上次被引擎
          结算的时刻」（被想起 / 被衰减都算一次结算）。好处：
          重复跑 ``decay`` 不会对同一条记忆反复叠加衰减（间隔≈0 则跳过）。
        * ``interference`` = 0.0 / 1.0（是否处在未裁决冲突里），见
          :meth:`_interference_set`。**不新增字段。**
        * ``rate`` 参数保留向后兼容，但语义变了：它不再等于「每次减多少」的
          线性步长，而是**整体缩放 lambda_D**（``None`` 时用
          ``config.memory.decay_rate``，其默认值正是 ``LAMBDA_BASE``，
          即缩放比 1.0）。``rate <= 0`` 直接返回 0。

        状态流转
        --------
        * ``strength < MEM_DORMANT_THRESHOLD(0.05)`` -> ``dormant``（休眠）
        * ``strength < weaken_threshold(0.15)``      -> ``weakened``

        **绝不删除任何记忆**；强度下限 ``MEM_RECALL_FLOOR``。
        """
        scale = float(rate if rate is not None else self.memory_cfg.decay_rate)
        if scale <= 0:
            return 0
        lam_scale = (scale / LAMBDA_BASE) if LAMBDA_BASE > 0 else 1.0
        alpha = float(getattr(self.memory_cfg, "decay_alpha", DECAY_ALPHA))
        beta = float(getattr(self.memory_cfg, "decay_beta", DECAY_BETA))
        gamma = float(getattr(self.memory_cfg, "decay_gamma", DECAY_GAMMA))
        dormant_th = float(getattr(self.memory_cfg, "dormant_threshold",
                                   MEM_DORMANT_THRESHOLD))

        rows = self.db.query(
            "SELECT memory_id, importance, emotional_intensity, recall_strength, "
            "       status, created_at, last_recalled, emotional_residue, "
            "       consolidation FROM memories WHERE status IN "
            "('active', 'reinforced', 'weakened')")
        interference = self._interference_set()
        now = now_ts()
        now_text = now_iso()
        touched = 0
        with self.db.transaction():
            for r in rows or []:
                mid = int(r["memory_id"])
                anchor = (_parse_iso(r.get("last_recalled"))
                          or _parse_iso(r.get("created_at")))
                if anchor is None:
                    continue
                dt_days = (now - anchor.timestamp()) / 86400.0
                if dt_days <= 0:
                    continue
                if dt_days * 1440.0 < DECAY_MIN_DELTA_MINUTES:
                    continue        # 不到 1 分钟不结算，避免空转刷时间戳

                er = _clamp(r.get("emotional_residue"), 0.0, 1.0, 0.0)
                cons = _clamp(r.get("consolidation"), 0.0, CONSOLIDATION_MAX,
                              DEFAULT_CONSOLIDATION)
                interf = 1.0 if mid in interference else 0.0
                lam = (LAMBDA_BASE * lam_scale
                       * (1.0 - alpha * er)
                       * (1.0 - beta * cons)
                       * (1.0 + gamma * interf))
                lam = max(0.0, lam)

                old = float(r.get("recall_strength") or DEFAULT_RECALL_STRENGTH)
                new = max(MEM_RECALL_FLOOR, old * math.exp(-lam * dt_days))

                old_status = str(r.get("status") or MEM_STATUS_ACTIVE)
                new_status = old_status
                if new < dormant_th:
                    new_status = MEM_STATUS_DORMANT
                elif new < self.memory_cfg.weaken_threshold:
                    if old_status in (MEM_STATUS_ACTIVE, MEM_STATUS_REINFORCED):
                        new_status = MEM_STATUS_WEAKENED

                if abs(new - old) < 1e-9 and new_status == old_status:
                    continue

                cur = self.db.execute(
                    "UPDATE memories SET recall_strength = ?, status = ?, "
                    "last_recalled = ? WHERE memory_id = ?",
                    (new, new_status, now_text, mid))
                if cur is not None:
                    touched += 1
        self.logger.info(
            "[记忆] 指数衰减完成：影响 %d 条（lambda_scale=%.3f 干扰=%d 条 "
            "ALPHA=%.2f BETA=%.2f GAMMA=%.2f）",
            touched, lam_scale, len(interference), alpha, beta, gamma)
        return touched

    # ==================================================================
    # 冲突（绝不覆盖旧记忆）
    # ==================================================================
    def record_conflict(
        self,
        owner: Any,
        old_memory_id: Any,
        new_memory_id: Any,
        old_belief: str = "",
        new_belief: str = "",
    ) -> Optional[int]:
        """登记一条记忆冲突，返回 ``conflict_id``。

        **本方法绝不修改、绝不删除任何一条 memories 记录**（SPEC 原则 12 /
        强制校验 14）。旧记忆与新记忆都原样保留，只多出一行冲突待裁决。
        """
        cid = self._resolve_owner(owner)
        if cid is None:
            self.logger.warning("[冲突] 拒绝登记：owner %r 无法解析", owner)
            return None
        old_mid = _to_int(old_memory_id)
        new_mid = _to_int(new_memory_id)
        if old_mid is None or new_mid is None:
            self.logger.warning("[冲突] 拒绝登记：memory_id 非法 %r / %r",
                                old_memory_id, new_memory_id)
            return None
        if old_mid == new_mid:
            self.logger.warning("[冲突] 拒绝登记：新旧是同一条记忆 %s", old_mid)
            return None

        existing = self.db.query_one(
            "SELECT conflict_id FROM memory_conflicts "
            "WHERE owner_character_id = ? AND old_memory_id = ? "
            "AND new_memory_id = ? AND status = ?",
            (cid, old_mid, new_mid, CONFLICT_STATUS_OPEN))
        if existing is not None:
            return int(existing["conflict_id"])

        conflict_id = self.db.insert(
            "INSERT INTO memory_conflicts "
            "(owner_character_id, old_memory_id, new_memory_id, old_belief, "
            " new_belief, status, resolution, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
            (cid, old_mid, new_mid,
             _bounded_str(old_belief, 1000), _bounded_str(new_belief, 1000),
             CONFLICT_STATUS_OPEN, now_iso()))
        if conflict_id is not None:
            self.logger.warning(
                "[冲突] 登记 conflict_id=%s owner=%s 旧=%s 新=%s "
                "（两条记忆都保留，不覆盖不删除）",
                conflict_id, cid, old_mid, new_mid)
        return conflict_id

    @staticmethod
    def _polarity(text: str) -> int:
        """极性：0 = 中性/正向，1 = 含否定。"""
        t = str(text or "")
        for marker in NEGATION_MARKERS:
            if marker in t:
                return 1
        return 0

    @staticmethod
    def _antonym_diff(a: str, b: str) -> bool:
        """两条文本是否命中反义对（一方含 X 另一方含 Y）。"""
        sa, sb = str(a or ""), str(b or "")
        for x, y in ANTONYM_PAIRS:
            if (x in sa and y in sb) or (y in sa and x in sb):
                return True
        return False

    def detect_conflicts(
        self,
        owner: Any,
        threshold: float = CONFLICT_SIMILARITY_THRESHOLD,
    ) -> int:
        """扫描同一角色的记忆，把"高相似但极性相反"的成对记为冲突。

        只**登记**冲突，不改动任何记忆（见 ``record_conflict``）。
        返回本次新增的冲突条数。
        """
        cid = self._resolve_owner(owner)
        if cid is None:
            return 0
        rows = self.db.query(
            "SELECT memory_id, memory_type, content, status FROM memories "
            "WHERE owner_character_id = ? AND is_consolidated = 0 "
            "AND status IN ('active', 'reinforced', 'weakened') "
            "ORDER BY memory_id ASC", (cid,))
        if len(rows) < 2:
            return 0

        created = 0
        pairs = 0
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                pairs += 1
                if pairs > CONFLICT_MAX_PAIRS_PER_RUN:
                    self.logger.warning("[冲突] 单轮比对上限 %d 已达，提前结束",
                                        CONFLICT_MAX_PAIRS_PER_RUN)
                    return created
                a, b = rows[i], rows[j]
                if str(a.get("memory_type")) != str(b.get("memory_type")):
                    continue
                ca, cb = str(a.get("content") or ""), str(b.get("content") or "")
                sim = _token_jaccard(ca, cb)
                if sim < float(threshold):
                    continue
                polar_diff = self._polarity(ca) != self._polarity(cb)
                if not (polar_diff or self._antonym_diff(ca, cb)):
                    continue
                if self.record_conflict(cid, a["memory_id"], b["memory_id"],
                                        ca, cb) is not None:
                    created += 1
        if created:
            self.logger.info("[冲突] 角色 %s 新增 %d 条冲突记录（相似度阈值 %.2f）",
                             cid, created, threshold)
        return created

    def list_conflicts(
        self,
        owner: Any = None,
        status: str = CONFLICT_STATUS_OPEN,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """列出冲突记录（附新旧记忆正文，便于人工裁决）。"""
        sql = (
            "SELECT cf.*, ao.content AS old_content, an.content AS new_content "
            "FROM memory_conflicts cf "
            "LEFT JOIN memories ao ON ao.memory_id = cf.old_memory_id "
            "LEFT JOIN memories an ON an.memory_id = cf.new_memory_id "
            "WHERE 1 = 1"
        )
        params: List[Any] = []
        if owner is not None:
            cid = self._resolve_owner(owner)
            if cid is None:
                return []
            sql += " AND cf.owner_character_id = ?"
            params.append(cid)
        if status:
            sql += " AND cf.status = ?"
            params.append(str(status))
        sql += " ORDER BY cf.conflict_id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def resolve_conflict(
        self,
        conflict_id: Any,
        resolution: str,
        supersede_old: bool = False,
    ) -> bool:
        """裁决一条冲突。

        ``supersede_old=True`` 时把旧记忆置为 ``superseded`` —— 这是**唯一**
        允许旧记忆离开 active 的合法路径，必须由人工/明确事实触发，绝不由
        LLM proposal 自动调用（SPEC 强制校验 14）。
        """
        cfid = _to_int(conflict_id)
        if cfid is None:
            return False
        row = self.db.query_one(
            "SELECT * FROM memory_conflicts WHERE conflict_id = ?", (cfid,))
        if row is None:
            self.logger.warning("[冲突] 裁决失败：%s 不存在", cfid)
            return False

        with self.db.transaction():
            cur = self.db.execute(
                "UPDATE memory_conflicts SET status = 'resolved', resolution = ? "
                "WHERE conflict_id = ?",
                (_bounded_str(resolution, 1000), cfid))
            if cur is None:
                return False
            if supersede_old:
                old_mid = _to_int(row.get("old_memory_id"))
                if old_mid is not None:
                    self.db.execute(
                        "UPDATE memories SET status = ? WHERE memory_id = ?",
                        (MEM_STATUS_SUPERSEDED, old_mid))
                    self.logger.info("[冲突] 旧记忆 %s 标记为 superseded（人工裁决）",
                                     old_mid)
        return True

    # ==================================================================
    # 压缩（consolidation）
    # ==================================================================
    def _llm_summarize(self, contents: Sequence[str]) -> Optional[str]:
        """调用 LLM 生成摘要；不可用或失败返回 None（调用方回退 raw）。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None
        body = "\n".join(f"- {c}" for c in contents if str(c).strip())
        if not body:
            return None
        system = (
            "你是记忆压缩器。把同一角色的多条相关记忆合并成一段简洁的摘要，"
            "要求：使用第三人称、保留所有关键事实与时间关系、不添加原文没有的信息、"
            "不超过 300 字、只输出摘要正文不要任何额外文字。"
        )
        user = f"请压缩以下 {len(contents)} 条记忆：\n{body}"
        try:
            out = self.llm.chat(system, user)
        except Exception as ex:
            self.logger.warning("[压缩] LLM 摘要异常：%s", ex)
            return None
        if not out or not str(out).strip():
            return None
        return str(out).strip()[:CONSOLIDATE_SUMMARY_MAX_LEN]

    def consolidate(
        self,
        owner: Any,
        threshold: Optional[int] = None,
        mode: str = CONSOLIDATED_MODE_RAW,
        memory_type: Optional[str] = None,
        allow_nested: bool = False,
        manual_trigger: bool = False,
    ) -> Optional[int]:
        """把某角色的同类型零散记忆压缩成一条摘要，返回摘要 ``memory_id``。

        规则（SPEC「记忆压缩」段）：

        * 只吃 ``status IN ('active','reinforced')`` **且** ``is_consolidated = 0``
        * 条数达到 ``threshold``（默认 5）才触发
        * 摘要条：``is_consolidated=1``、``status='active'``、
          ``consolidated_from`` 记原始 id 数组
        * 原始条：``status='weakened'``、``recall_strength *= 0.5``
        * **绝不删除原始记忆**
        * 摘要**默认不参与下一轮**（``is_consolidated=1`` 被硬过滤）；
          只有显式传 ``allow_nested=True`` 才允许二次整合
        * ``mode='raw'`` 用拼接 + 300 字截断；``mode='llm'/'deep'`` 先试
          LLM，失败自动回退 raw
        * **[tier1 保护] ``manual_trigger=False``（默认，自动轮）时跳过
          tier1 核心记忆**（身份 / 核心关系 / 不可逆事件）；
          ``manual_trigger=True`` 不设该条件（允许手动压缩 tier1）
        """
        cid = self._resolve_owner(owner)
        if cid is None:
            return None
        thr = int(threshold or self.memory_cfg.consolidate_threshold)
        md = str(mode or CONSOLIDATED_MODE_RAW).strip().lower()
        want_llm = md in LLM_MODES

        sql = (
            "SELECT memory_id, memory_type, content, importance, confidence, "
            "       emotional_intensity, tags FROM memories "
            "WHERE owner_character_id = ? AND status IN ('active', 'reinforced') "
            "AND (is_consolidated = 0" + (" OR is_consolidated = 1" if allow_nested else "") + ")"
        )
        params: List[Any] = [cid]
        # [tier1 保护] 自动轮（manual_trigger=False）跳过 tier1 核心记忆；
        #              手动轮不设该条件（允许手动压缩 tier1）。
        if not manual_trigger:
            sql += " AND tier <> ?"
            params.append(TIER_CORE)
        if memory_type is not None:
            sql += " AND memory_type = ?"
            params.append(str(memory_type).strip().lower())
        sql += " ORDER BY memory_id ASC"
        rows = self.db.query(sql, tuple(params))
        if len(rows) < thr:
            return None

        # 按 memory_type 分组，只压缩数量够的那一组
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(str(r.get("memory_type") or DEFAULT_MEMORY_TYPE),
                              []).append(r)

        best_type = ""
        best_group: List[Dict[str, Any]] = []
        for mt, group in groups.items():
            if len(group) >= thr and len(group) > len(best_group):
                best_type, best_group = mt, group
        if not best_group:
            return None

        contents = [str(g.get("content") or "") for g in best_group]
        mode_used = CONSOLIDATED_MODE_RAW
        summary = ""
        if want_llm:
            llm_out = self._llm_summarize(contents)
            if llm_out:
                summary, mode_used = llm_out, CONSOLIDATED_MODE_LLM
            else:
                self.logger.warning("[压缩] LLM 摘要不可用，回退 raw 模式")
        if not summary:
            joined = "；".join(c for c in contents if c)
            summary = joined[:CONSOLIDATE_SUMMARY_MAX_LEN]
            mode_used = CONSOLIDATED_MODE_RAW
        if not summary.strip():
            return None

        src_ids = [int(g["memory_id"]) for g in best_group]
        tags: List[str] = []
        for g in best_group:
            for t in _as_list(g.get("tags")):
                if str(t) not in tags:
                    tags.append(str(t))

        with self.db.transaction():
            summary_id = self.add_memory(
                owner=cid,
                content=summary,
                memory_type=best_type,
                source_type=_inherit_source_type(best_group),
                importance=max((_clamp(g.get("importance"), 0, 1, DEFAULT_IMPORTANCE)
                                for g in best_group), default=DEFAULT_IMPORTANCE),
                confidence=(sum(_clamp(g.get("confidence"), 0, 1, DEFAULT_CONFIDENCE)
                                for g in best_group) / len(best_group)),
                emotional_intensity=max(
                    (_clamp(g.get("emotional_intensity"), 0, 1,
                            DEFAULT_EMOTIONAL_INTENSITY) for g in best_group),
                    default=DEFAULT_EMOTIONAL_INTENSITY),
                is_subjective=False,
                tags=tags,
                dedup=False,
                status=MEM_STATUS_ACTIVE,
                is_consolidated=True,
                consolidated_from=src_ids,
                consolidated_mode=mode_used,
            )
            if summary_id is None:
                self.logger.warning("[压缩] 摘要写入失败，原始记忆保持不动")
                return None

            marks = ", ".join("?" * len(src_ids))
            # 原始记忆：只降强度 + 置 weakened，绝不删除
            cur = self.db.execute(
                f"UPDATE memories SET status = ?, "
                f"recall_strength = MAX(?, recall_strength * ?) "
                f"WHERE memory_id IN ({marks})",
                tuple([MEM_STATUS_WEAKENED, MEM_RECALL_FLOOR,
                       CONSOLIDATED_SOURCE_FACTOR] + src_ids))
            if cur is None:
                self.logger.warning("[压缩] 原始记忆强度下调失败（记忆仍在，未被删除）")

        self.logger.info(
            "[压缩] owner=%s type=%s %d 条 -> 摘要 memory_id=%s（模式 %s）",
            cid, best_type, len(src_ids), summary_id, mode_used)
        return int(summary_id)

    def consolidate_all(
        self,
        mode: str = CONSOLIDATED_MODE_RAW,
        threshold: Optional[int] = None,
        manual_trigger: bool = False,
    ) -> int:
        """对所有有记忆的角色各跑一轮压缩，返回新建摘要的条数。

        ``manual_trigger=False``（默认）时每轮都跳过 tier1 核心记忆；
        手动轮（``True``）不设该条件。
        """
        owners = self.db.query(
            "SELECT DISTINCT owner_character_id AS cid FROM memories "
            "WHERE is_consolidated = 0 AND status IN ('active', 'reinforced')")
        made = 0
        for r in owners:
            while True:
                out = self.consolidate(r["cid"], threshold=threshold, mode=mode,
                                       manual_trigger=manual_trigger)
                if out is None:
                    break
                made += 1
        self.logger.info("[压缩] 全库压缩完成：新增摘要 %d 条（manual=%s）",
                         made, manual_trigger)
        return made


# ==============================================================================
# 11. KnowledgeManager —— 非事件型知识
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【10】知识 + 信念
# ══════════════════════════════════════════════════════════════════════

class KnowledgeManager:
    """``knowledge`` 表的管理者 —— **只存非事件型事实**。

    与 ``event_visibility`` 的严格分工（SPEC 原则 2 / 强制校验 8、9、10）：

    * 事件型信息（"昨晚谁去了二楼"）**只**写 ``event_visibility``
    * 非事件型事实（"明喜欢吃苹果"）**只**写 ``knowledge``
    * 两者不得互相替代，同一信息不得存两遍
    * ``knowledge.event_id`` 是**兼容字段**：V2 新写入的非事件型 knowledge
      默认必须为 NULL。调用方传入非空 ``event_id`` 会被**拒绝**，因为那等于
      把事件型知识绕过 ``event_visibility`` 塞进 knowledge。
      仅在明确迁移旧数据时可用 ``allow_event_link=True`` 放行。
    * 禁止把 knowledge 内容镜像成 ``beliefs.kind='FACT'``（FACT 只用于事件型）
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.logger = logger or _get_logger("knowledge")

    # ------------------------------------------------------------------
    def _resolve_owner(self, owner: Any) -> Optional[int]:
        if self.char_mgr is None:
            return _to_int(owner)
        return self.char_mgr.resolve_id(owner)

    @staticmethod
    def _dedup_hash(owner_id: int, subject: str) -> str:
        return _sha(f"know|{owner_id}|{_WS_RE.sub('', subject or '')}")

    @staticmethod
    def _validate_status(status: Any) -> Optional[str]:
        st = str(status or DEFAULT_KNOWLEDGE_STATUS).strip().upper()
        return st if st in VALID_KNOWLEDGE_STATUSES else None

    # ------------------------------------------------------------------
    def set_knowledge(
        self,
        owner: Any,
        subject: str,
        status: str = DEFAULT_KNOWLEDGE_STATUS,
        event_id: Optional[int] = None,
        confidence: float = 0.5,
        source: Optional[str] = None,
        allow_event_link: bool = False,
    ) -> Optional[int]:
        """写入 / 更新一条非事件型知识，返回 ``knowledge_id``。

        ``(owner, subject)`` 是逻辑唯一键：已存在则更新 status / confidence /
        source，不产生第二行。
        """
        cid = self._resolve_owner(owner)
        if cid is None:
            self.logger.warning("[知识] 拒绝写入：owner %r 无法解析", owner)
            return None

        subj = _bounded_str(subject, MEM_CONTENT_MAX_LEN)
        if not subj:
            self.logger.warning("[知识] 拒绝写入：subject 为空（owner=%s）", cid)
            return None

        st = self._validate_status(status)
        if st is None:
            self.logger.warning("[知识] 拒绝写入：非法 status %r（应为 %s）",
                                status, VALID_KNOWLEDGE_STATUSES)
            return None

        # ---- 校验 9：非事件型 knowledge 的 event_id 必须为 NULL ----
        ev_id = _to_int(event_id)
        if ev_id is not None and not allow_event_link:
            self.logger.warning(
                "[知识] 拒绝写入：非事件型 knowledge 的 event_id 必须为 NULL"
                "（收到 %s）—— 事件型信息请走 event_visibility", ev_id)
            return None
        if ev_id is not None:
            if self.db.query_one(
                    "SELECT event_id FROM events WHERE event_id = ?",
                    (ev_id,)) is None:
                self.logger.warning("[知识] 拒绝写入：event_id=%s 不存在", ev_id)
                return None

        now = now_iso()
        dh = self._dedup_hash(cid, subj)
        existing = self.db.query_one(
            "SELECT knowledge_id FROM knowledge WHERE owner_character_id = ? "
            "AND dedup_hash = ? LIMIT 1", (cid, dh))

        if existing is not None:
            kid = int(existing["knowledge_id"])
            cur = self.db.execute(
                "UPDATE knowledge SET status = ?, event_id = ?, confidence = ?, "
                "source = ?, updated_at = ? WHERE knowledge_id = ?",
                (st, ev_id,
                 _clamp(confidence, 0.0, 1.0, 0.5),
                 _bounded_str(source, MAX_SOURCE_LEN) or None, now, kid))
            if cur is None:
                return None
            self.logger.info("[知识] 更新 id=%s owner=%s status=%s subject=%s",
                             kid, cid, st, subj[:30])
            return kid

        kid = self.db.insert(
            "INSERT INTO knowledge "
            "(owner_character_id, subject, event_id, status, confidence, source, "
            " created_at, updated_at, dedup_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, subj, ev_id, st, _clamp(confidence, 0.0, 1.0, 0.5),
             _bounded_str(source, MAX_SOURCE_LEN) or None, now, now, dh))
        if kid is None:
            return None
        self.logger.info("[知识] 新建 id=%s owner=%s status=%s subject=%s",
                         kid, cid, st, subj[:30])
        return int(kid)

    # ------------------------------------------------------------------
    def get_knowledge(self, knowledge_id: Any) -> Optional[Dict[str, Any]]:
        """按 id 取知识条目。"""
        kid = _to_int(knowledge_id)
        if kid is None:
            return None
        return self.db.query_one(
            "SELECT * FROM knowledge WHERE knowledge_id = ?", (kid,))

    def get_by_status(
        self,
        owner: Any,
        statuses: Union[str, Sequence[str]] = KN_KNOWN,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """按状态（可多个）取某角色的知识，新 -> 旧。"""
        cid = self._resolve_owner(owner)
        if cid is None:
            return []
        if isinstance(statuses, str):
            status_list = [statuses]
        else:
            status_list = list(statuses or [])
        if not status_list:
            return []
        status_list = [s for s in (self._validate_status(s) for s in status_list) if s]
        if not status_list:
            return []
        marks = ", ".join("?" * len(status_list))
        sql = (f"SELECT * FROM knowledge WHERE owner_character_id = ? "
               f"AND status IN ({marks}) "
               f"ORDER BY updated_at DESC, knowledge_id DESC")
        params: List[Any] = [cid] + status_list
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def get_known(self, owner: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """该角色确认知道的事实。"""
        return self.get_by_status(owner, [KN_KNOWN], limit)

    def get_unknown(self, owner: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """该角色明确不知道的事实（knowledge 表允许存 UNKNOWN，与 visibility 不同）。"""
        return self.get_by_status(owner, [KN_UNKNOWN], limit)

    def get_suspected(self, owner: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """该角色怀疑 / 听说的事实。"""
        return self.get_by_status(owner, [KN_SUSPECTED, KN_RUMORED], limit)

    def get_forgotten(self, owner: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """该角色已遗忘的事实。"""
        return self.get_by_status(owner, [KN_FORGOTTEN], limit)

    def list_for(self, owner: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """该角色的全部知识条目（不限状态）。"""
        cid = self._resolve_owner(owner)
        if cid is None:
            return []
        sql = ("SELECT * FROM knowledge WHERE owner_character_id = ? "
               "ORDER BY updated_at DESC, knowledge_id DESC")
        params: List[Any] = [cid]
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def get_by_subject(
        self,
        owner: Any,
        subject_keyword: str,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """按 subject 关键词模糊查（用于 ContextBuilder 组装"从某人那里知道的事"）。"""
        cid = self._resolve_owner(owner)
        if cid is None:
            return []
        kw = str(subject_keyword or "").strip()
        if not kw:
            return []
        sql = ("SELECT * FROM knowledge WHERE owner_character_id = ? "
               "AND subject LIKE ?")
        params: List[Any] = [cid, f"%{kw}%"]
        if statuses:
            status_list = [s for s in (self._validate_status(s) for s in statuses) if s]
            if status_list:
                marks = ", ".join("?" * len(status_list))
                sql += f" AND status IN ({marks})"
                params.extend(status_list)
        sql += " ORDER BY updated_at DESC, knowledge_id DESC"
        return self.db.query(sql, tuple(params))

    def count_by_status(self, owner: Any = None) -> Dict[str, int]:
        """按状态统计知识条数。"""
        out = {s: 0 for s in VALID_KNOWLEDGE_STATUSES}
        if owner is None:
            rows = self.db.query(
                "SELECT status, COUNT(*) AS c FROM knowledge GROUP BY status")
        else:
            cid = self._resolve_owner(owner)
            if cid is None:
                return out
            rows = self.db.query(
                "SELECT status, COUNT(*) AS c FROM knowledge "
                "WHERE owner_character_id = ? GROUP BY status", (cid,))
        for r in rows:
            out[str(r["status"])] = int(r["c"])
        return out

    def count(self, owner: Any = None) -> int:
        """知识条数。"""
        if owner is None:
            return self.db.count("knowledge")
        cid = self._resolve_owner(owner)
        if cid is None:
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM knowledge WHERE owner_character_id = ?",
            (cid,), 0) or 0)


# ==============================================================================
# 12. BeliefManager —— 信念（kind 分类）
# ==============================================================================

class BeliefManager:
    """``beliefs`` 表的管理者。

    ``kind`` 五分类（SPEC 枚举）：

    * ``FACT``        —— 角色确认/记住的**事件型**事实。
                        **只能由规则层产出**（``generated_by='rule'``）；
                        LLM 提出 FACT 一律拒绝（强制校验 2 / 10）
    * ``BELIEF``      —— 角色相信的事
    * ``ATTITUDE``    —— 角色对某人的态度
    * ``SELF_BELIEF`` —— 角色对自己的看法
    * ``JUDGMENT``    —— 角色对某事的判断

    非事件型事实（"明喜欢吃苹果"）**不进 FACT belief，只进 knowledge**
    （强制校验 10）。

    ``status`` 单向流转（强制校验 3）：只允许 ``active -> superseded /
    contradicted / archived``，反向一律拒绝。要改回来必须新建一行，旧行保留。
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.logger = logger or _get_logger("beliefs")

    # ------------------------------------------------------------------
    def _resolve_owner(self, owner: Any) -> Optional[int]:
        if self.char_mgr is None:
            return _to_int(owner)
        return self.char_mgr.resolve_id(owner)

    @staticmethod
    def _dedup_hash(owner_id: int, kind: str, subject_ref: str,
                    statement: str) -> str:
        return _sha(f"bel|{owner_id}|{kind}|{subject_ref or ''}|"
                    f"{_WS_RE.sub('', statement or '')}")

    # ------------------------------------------------------------------
    def add_belief(
        self,
        owner: Any,
        kind: str,
        subject_kind: str,
        statement: str,
        subject_ref: Optional[str] = None,
        confidence: float = DEFAULT_BELIEF_CONFIDENCE,
        based_on_event_id: Optional[int] = None,
        generated_by: str = GENERATED_BY_RULE,
        source: Optional[str] = None,
        based_on_belief_id: Optional[int] = None,
        tags: Optional[Sequence[Any]] = None,
        dedup: bool = True,
    ) -> Optional[int]:
        """写入一条信念，返回 ``belief_id``；被校验拦下返回 None。

        关键闸门（顺序）：

        1. ``kind`` ∈ {FACT, BELIEF, ATTITUDE, SELF_BELIEF, JUDGMENT}
        2. ``generated_by`` ∈ {rule, llm}
        3. **``kind='FACT'`` 时 ``generated_by`` 必须是 ``'rule'``** ——
           拒绝 LLM 生成 FACT
        4. ``generated_by='llm'`` 时 ``kind`` 不得是 FACT（与 3 互为正反）
        5. ``subject_kind`` ∈ {person, event, fact, self}
        """
        cid = self._resolve_owner(owner)
        if cid is None:
            self.logger.warning("[信念] 拒绝写入：owner %r 无法解析", owner)
            return None

        stmt = _bounded_str(statement, MEM_CONTENT_MAX_LEN)
        if not stmt:
            self.logger.warning("[信念] 拒绝写入：statement 为空（owner=%s）", cid)
            return None

        kd = str(kind or "").strip().upper()
        if kd not in VALID_BELIEF_KINDS:
            self.logger.warning("[信念] 拒绝写入：非法 kind %r（应为 %s）",
                                kind, VALID_BELIEF_KINDS)
            return None

        gen = str(generated_by or GENERATED_BY_RULE).strip().lower()
        if gen not in VALID_BELIEF_GENERATORS:
            self.logger.warning("[信念] 拒绝写入：非法 generated_by %r", generated_by)
            return None

        # ---- 强制校验 2 / 10：FACT 只能由规则层产出 ----
        if kd == BELIEF_FACT and gen != GENERATED_BY_RULE:
            self.logger.warning(
                "[信念] 拒绝写入：kind=FACT 必须 generated_by='rule'"
                "（收到 %r）—— 禁止 LLM 生成 FACT", generated_by)
            return None
        if gen == GENERATED_BY_LLM and kd not in LLM_WRITABLE_BELIEF_KINDS:
            self.logger.warning(
                "[信念] 拒绝写入：LLM 只能写 %s，不能写 %s",
                LLM_WRITABLE_BELIEF_KINDS, kd)
            return None

        sk = str(subject_kind or "").strip().lower()
        if sk not in VALID_BELIEF_SUBJECT_KINDS:
            self.logger.warning("[信念] 拒绝写入：非法 subject_kind %r（应为 %s）",
                                subject_kind, VALID_BELIEF_SUBJECT_KINDS)
            return None

        ev_id = _to_int(based_on_event_id)
        if ev_id is not None and self.db.query_one(
                "SELECT event_id FROM events WHERE event_id = ?", (ev_id,)) is None:
            self.logger.warning("[信念] 拒绝写入：based_on_event_id=%s 不存在", ev_id)
            return None
        bb_id = _to_int(based_on_belief_id)
        if bb_id is not None and self.db.query_one(
                "SELECT belief_id FROM beliefs WHERE belief_id = ?",
                (bb_id,)) is None:
            self.logger.warning("[信念] 拒绝写入：based_on_belief_id=%s 不存在", bb_id)
            return None

        ref = _bounded_str(subject_ref, 256) or None
        dh = self._dedup_hash(cid, kd, ref or "", stmt)
        if dedup:
            row = self.db.query_one(
                "SELECT belief_id FROM beliefs WHERE owner_character_id = ? "
                "AND dedup_hash = ? AND status = ? LIMIT 1",
                (cid, dh, BELIEF_STATUS_ACTIVE))
            if row is not None:
                self.logger.debug("[信念] 已存在同内容 active 信念，复用 id=%s",
                                  row["belief_id"])
                return int(row["belief_id"])

        now = now_iso()
        tag_list = [str(t).strip() for t in _as_list(tags) if str(t).strip()]
        belief_id = self.db.insert(
            "INSERT INTO beliefs "
            "(owner_character_id, kind, subject_kind, subject_ref, statement, "
            " confidence, based_on_event_id, based_on_belief_id, generated_by, "
            " source, status, superseded_by, formed_at, updated_at, tags, dedup_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)",
            (cid, kd, sk, ref, stmt,
             _clamp(confidence, 0.0, 1.0, DEFAULT_BELIEF_CONFIDENCE),
             ev_id, bb_id, gen,
             _bounded_str(source, MAX_SOURCE_LEN) or None,
             BELIEF_STATUS_ACTIVE, now, now,
             _json_dumps(tag_list), dh))
        if belief_id is None:
            return None
        self.logger.info("[信念] 新建 id=%s owner=%s kind=%s subject=%s/%s by=%s",
                         belief_id, cid, kd, sk, ref or "-", gen)
        return int(belief_id)

    # ------------------------------------------------------------------
    def get_belief(self, belief_id: Any) -> Optional[Dict[str, Any]]:
        """按 id 取信念。"""
        bid = _to_int(belief_id)
        if bid is None:
            return None
        return self.db.query_one(
            "SELECT * FROM beliefs WHERE belief_id = ?", (bid,))

    def list_for(
        self,
        owner: Any,
        kind: Optional[str] = None,
        status: Optional[str] = BELIEF_STATUS_ACTIVE,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """列出某角色的信念（可按 kind / status 过滤；status=None 表示不限）。"""
        cid = self._resolve_owner(owner)
        if cid is None:
            return []
        sql = "SELECT * FROM beliefs WHERE owner_character_id = ?"
        params: List[Any] = [cid]
        if kind is not None:
            kd = str(kind).strip().upper()
            if kd not in VALID_BELIEF_KINDS:
                self.logger.warning("[信念] list_for 收到非法 kind %r", kind)
                return []
            sql += " AND kind = ?"
            params.append(kd)
        if status is not None:
            st = str(status).strip().lower()
            if st not in VALID_BELIEF_STATUSES:
                self.logger.warning("[信念] list_for 收到非法 status %r", status)
                return []
            sql += " AND status = ?"
            params.append(st)
        sql += " ORDER BY confidence DESC, belief_id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def list_by_subject(
        self,
        owner: Any,
        subject_kind: str,
        subject_ref: str,
        status: Optional[str] = BELIEF_STATUS_ACTIVE,
    ) -> List[Dict[str, Any]]:
        """按 subject（如"角色 X 对 Y 的态度"）取信念。"""
        cid = self._resolve_owner(owner)
        if cid is None:
            return []
        sk = str(subject_kind or "").strip().lower()
        if sk not in VALID_BELIEF_SUBJECT_KINDS:
            self.logger.warning("[信念] list_by_subject 收到非法 subject_kind %r",
                                subject_kind)
            return []
        sql = ("SELECT * FROM beliefs WHERE owner_character_id = ? "
               "AND subject_kind = ? AND subject_ref = ?")
        params: List[Any] = [cid, sk, str(subject_ref or "").strip()]
        if status is not None:
            sql += " AND status = ?"
            params.append(str(status).strip().lower())
        sql += " ORDER BY confidence DESC, belief_id DESC"
        return self.db.query(sql, tuple(params))

    def count_by_status(self, owner: Any = None) -> Dict[str, int]:
        """按状态统计信念条数。"""
        out = {s: 0 for s in VALID_BELIEF_STATUSES}
        if owner is None:
            rows = self.db.query(
                "SELECT status, COUNT(*) AS c FROM beliefs GROUP BY status")
        else:
            cid = self._resolve_owner(owner)
            if cid is None:
                return out
            rows = self.db.query(
                "SELECT status, COUNT(*) AS c FROM beliefs "
                "WHERE owner_character_id = ? GROUP BY status", (cid,))
        for r in rows:
            out[str(r["status"])] = int(r["c"])
        return out

    def count(self, owner: Any = None) -> int:
        """信念条数。"""
        if owner is None:
            return self.db.count("beliefs")
        cid = self._resolve_owner(owner)
        if cid is None:
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM beliefs WHERE owner_character_id = ?",
            (cid,), 0) or 0)

    # ------------------------------------------------------------------
    # 状态流转（单向，强制校验 3）
    # ------------------------------------------------------------------
    def set_status(
        self,
        belief_id: Any,
        status: str,
        superseded_by: Optional[int] = None,
    ) -> bool:
        """变更信念状态，只允许 ``active -> superseded/contradicted/archived``。

        反向（superseded -> active 等）一律拒绝并 ``logging.warning``
        —— 要"改回来"必须新建一行，旧行保留（SPEC 强制校验 3）。
        """
        bid = _to_int(belief_id)
        if bid is None:
            return False
        row = self.get_belief(bid)
        if row is None:
            self.logger.warning("[信念] set_status 失败：%s 不存在", bid)
            return False

        old = str(row.get("status") or BELIEF_STATUS_ACTIVE).strip().lower()
        new = str(status or "").strip().lower()
        if new not in VALID_BELIEF_STATUSES:
            self.logger.warning("[信念] set_status 失败：非法 status %r", status)
            return False
        if new == old:
            return True

        if old != BELIEF_LEAVABLE_STATUS:
            self.logger.warning(
                "[信念] 拒绝流转：id=%s 已处于终态 %s，不能改为 %s"
                "（单向不可逆，需新建一行）", bid, old, new)
            return False
        if new not in BELIEF_TARGET_STATUSES:
            self.logger.warning(
                "[信念] 拒绝流转：只允许 active -> %s，收到 %s",
                BELIEF_TARGET_STATUSES, new)
            return False

        sb = _to_int(superseded_by)
        if new == BELIEF_STATUS_SUPERSEDED:
            if sb is None:
                self.logger.warning(
                    "[信念] 拒绝流转：目标状态为 superseded 时必须提供 superseded_by"
                    "（id=%s）", bid)
                return False
            if sb == bid:
                self.logger.warning("[信念] 拒绝流转：superseded_by 不能是自己（id=%s）",
                                    bid)
                return False
            if self.get_belief(sb) is None:
                self.logger.warning("[信念] 拒绝流转：superseded_by=%s 不存在", sb)
                return False

        cur = self.db.execute(
            "UPDATE beliefs SET status = ?, superseded_by = ?, updated_at = ? "
            "WHERE belief_id = ?",
            (new, sb, now_iso(), bid))
        if cur is None:
            return False
        self.logger.info("[信念] id=%s 状态 %s -> %s%s",
                         bid, old, new, f"（被 {sb} 取代）" if sb else "")
        return True

    def supersede(
        self,
        belief_id: Any,
        new_belief_id: Any,
        reason: str = "",
    ) -> bool:
        """用一条新信念取代旧信念：旧行 ``status='superseded'`` 且写
        ``superseded_by=new_belief_id``；**旧行保留不删**。
        """
        bid = _to_int(belief_id)
        nid = _to_int(new_belief_id)
        if bid is None or nid is None:
            self.logger.warning("[信念] supersede 参数非法：%r / %r",
                                belief_id, new_belief_id)
            return False
        if bid == nid:
            self.logger.warning("[信念] supersede 失败：新旧是同一条 %s", bid)
            return False
        if self.get_belief(nid) is None:
            self.logger.warning("[信念] supersede 失败：新信念 %s 不存在", nid)
            return False

        ok = self.set_status(bid, BELIEF_STATUS_SUPERSEDED, superseded_by=nid)
        if ok and reason:
            self.db.execute(
                "UPDATE beliefs SET source = COALESCE(source, '') || ? "
                "WHERE belief_id = ?",
                (f" | superseded_reason: {_bounded_str(reason, 200)}", bid))
        return ok

    def mark_contradicted(self, belief_id: Any, reason: str = "") -> bool:
        """标记为被证据推翻。"""
        ok = self.set_status(belief_id, BELIEF_STATUS_CONTRADICTED)
        if ok and reason:
            self.logger.info("[信念] id=%s 标记 contradicted：%s", belief_id, reason)
        return ok

    def mark_archived(self, belief_id: Any, reason: str = "") -> bool:
        """归档。"""
        ok = self.set_status(belief_id, BELIEF_STATUS_ARCHIVED)
        if ok and reason:
            self.logger.info("[信念] id=%s 归档：%s", belief_id, reason)
        return ok


# ==============================================================================
# 13. AssociationManager —— 记忆关联
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【11】关联 + 关系 + 状态
# ══════════════════════════════════════════════════════════════════════

class AssociationManager:
    """``associations`` 表的管理者（记忆之间的无向关联）。

    * ``(memory_a, memory_b, assoc_type)`` 唯一；本类统一把小的 id 放
      ``memory_a``，避免 (1,2) 与 (2,1) 重复两条
    * 只做关联，不改动任何记忆内容
    * ``auto_link_by_tokens`` 用分词 Jaccard 相似度自动成链
    """

    def __init__(
        self,
        db: Database,
        config: Optional[Config] = None,
        mem_mgr: Optional[MemoryManager] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.config = config
        self.mem_mgr = mem_mgr
        self.logger = logger or _get_logger("associations")

    # ------------------------------------------------------------------
    @staticmethod
    def _ordered(a: Any, b: Any) -> Optional[Tuple[int, int]]:
        """规范化 id 顺序（小在前），自关联返回 None。"""
        if isinstance(a, bool) or isinstance(b, bool):
            return None
        ia, ib = _to_int(a), _to_int(b)
        if ia is None or ib is None or ia == ib:
            return None
        return (ia, ib) if ia < ib else (ib, ia)

    def _memory_exists(self, memory_id: int) -> bool:
        return self.db.query_one(
            "SELECT memory_id FROM memories WHERE memory_id = ?",
            (int(memory_id),)) is not None

    # ------------------------------------------------------------------
    def link(
        self,
        memory_a: Any,
        memory_b: Any,
        assoc_type: str = ASSOC_DEFAULT_TYPE,
        weight: float = 1.0,
    ) -> Optional[int]:
        """建立 / 更新一条记忆关联，返回 ``assoc_id``。

        weight 夹取到 0.0~1.0；重复关联同一对时更新权重而不是新增一行。
        """
        pair = self._ordered(memory_a, memory_b)
        if pair is None:
            self.logger.warning("[关联] 拒绝：memory_id 非法或自关联 %r / %r",
                                memory_a, memory_b)
            return None
        a, b = pair
        if not self._memory_exists(a) or not self._memory_exists(b):
            self.logger.warning("[关联] 拒绝：记忆 %s 或 %s 不存在", a, b)
            return None

        at = _bounded_str(assoc_type, 64) or ASSOC_DEFAULT_TYPE
        w = _clamp(weight, 0.0, 1.0, 1.0)

        existing = self.db.query_one(
            "SELECT assoc_id FROM associations "
            "WHERE memory_a = ? AND memory_b = ? AND assoc_type = ?", (a, b, at))
        if existing is not None:
            aid = int(existing["assoc_id"])
            self.db.execute(
                "UPDATE associations SET weight = ? WHERE assoc_id = ?", (w, aid))
            return aid

        aid = self.db.insert(
            "INSERT INTO associations(memory_a, memory_b, assoc_type, weight, "
            "created_at) VALUES(?, ?, ?, ?, ?)",
            (a, b, at, w, now_iso()))
        if aid is not None:
            self.logger.debug("[关联] %s <-> %s（%s, w=%.2f）", a, b, at, w)
        return int(aid) if aid is not None else None

    def unlink(
        self,
        memory_a: Any,
        memory_b: Any,
        assoc_type: Optional[str] = None,
    ) -> bool:
        """删除一条关联（**只删关联，不碰记忆本身**）。"""
        pair = self._ordered(memory_a, memory_b)
        if pair is None:
            return False
        a, b = pair
        if assoc_type:
            cur = self.db.execute(
                "DELETE FROM associations WHERE memory_a = ? AND memory_b = ? "
                "AND assoc_type = ?",
                (a, b, _bounded_str(assoc_type, 64)))
        else:
            cur = self.db.execute(
                "DELETE FROM associations WHERE memory_a = ? AND memory_b = ?",
                (a, b))
        return cur is not None

    def get_links(
        self,
        memory_id: Any,
        assoc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """取与某条记忆相关的全部关联行。"""
        mid = _to_int(memory_id)
        if mid is None:
            return []
        sql = "SELECT * FROM associations WHERE memory_a = ? OR memory_b = ?"
        params: List[Any] = [mid, mid]
        if assoc_type:
            sql += " AND assoc_type = ?"
            params.append(_bounded_str(assoc_type, 64))
        sql += " ORDER BY weight DESC, assoc_id ASC"
        return self.db.query(sql, tuple(params))

    def neighbours(
        self,
        memory_id: Any,
        limit: Optional[int] = None,
        assoc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """取邻居记忆（含正文与权重）。"""
        mid = _to_int(memory_id)
        if mid is None:
            return []
        links = self.get_links(mid, assoc_type)
        if not links:
            return []
        other_ids: List[int] = []
        weights: Dict[int, float] = {}
        for lk in links:
            other = (int(lk["memory_b"]) if int(lk["memory_a"]) == mid
                     else int(lk["memory_a"]))
            if other in weights:
                continue
            weights[other] = _clamp(lk.get("weight"), 0.0, 1.0, 1.0)
            other_ids.append(other)
        if not other_ids:
            return []
        marks = ", ".join("?" * len(other_ids))
        rows = self.db.query(
            f"SELECT * FROM memories WHERE memory_id IN ({marks})", tuple(other_ids))
        for r in rows:
            r["_weight"] = weights.get(int(r["memory_id"]), 1.0)
        rows.sort(key=lambda r: (-float(r.get("_weight") or 0), int(r["memory_id"])))
        if limit:
            rows = rows[:int(limit)]
        return rows

    def get_neighbours(
        self,
        memory_id: Any,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """``neighbours`` 的别名（兼容不同调用习惯）。"""
        return self.neighbours(memory_id, limit=limit)

    def auto_link_by_tokens(
        self,
        memory_id: Any,
        content: Optional[str] = None,
        owner_id: Optional[Any] = None,
        threshold: float = ASSOC_AUTO_LINK_THRESHOLD,
        memory_type: Optional[str] = None,
    ) -> int:
        """按 token 相似度，把一条记忆与同角色其他记忆自动关联。

        ``content`` / ``owner_id`` 省略时从库里回查。返回新建的关联条数。
        """
        mid = _to_int(memory_id)
        if mid is None:
            return 0
        row = self.db.query_one(
            "SELECT memory_id, owner_character_id, memory_type, content "
            "FROM memories WHERE memory_id = ?", (mid,))
        if row is None:
            self.logger.warning("[关联] auto_link 失败：记忆 %s 不存在", mid)
            return 0

        text = str(content if content is not None else row.get("content") or "")
        cid = _to_int(owner_id if owner_id is not None
                      else row.get("owner_character_id"))
        if cid is None or not text.strip():
            return 0
        mt = memory_type if memory_type is not None else row.get("memory_type")

        sql = ("SELECT memory_id, content FROM memories "
               "WHERE owner_character_id = ? AND memory_id != ? "
               "AND is_consolidated = 0")
        params: List[Any] = [cid, mid]
        if mt is not None:
            sql += " AND memory_type = ?"
            params.append(str(mt))
        sql += " ORDER BY memory_id DESC LIMIT 200"
        candidates = self.db.query(sql, tuple(params))

        made = 0
        scored: List[Tuple[float, int]] = []
        for cand in candidates:
            sim = _token_jaccard(text, cand.get("content"))
            if sim >= float(threshold):
                scored.append((sim, int(cand["memory_id"])))
        scored.sort(key=lambda p: -p[0])
        for sim, other in scored[:ASSOC_MAX_AUTO_LINKS]:
            if self.link(mid, other, ASSOC_DEFAULT_TYPE, sim) is not None:
                made += 1
        if made:
            self.logger.debug("[关联] 记忆 %s 自动关联 %d 条（阈值 %.2f）",
                              mid, made, threshold)
        return made

    def count(self, memory_id: Optional[Any] = None) -> int:
        """关联总数（传 memory_id 则统计该记忆的关联数）。"""
        if memory_id is None:
            return self.db.count("associations")
        mid = _to_int(memory_id)
        if mid is None:
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM associations WHERE memory_a = ? OR memory_b = ?",
            (mid, mid), 0) or 0)


# ==============================================================================
# 第 3 批：关系 / 状态 / 承诺 / 秘密 —— RelationshipManager / StateManager /
#          CommitmentManager / SecretManager
# ==============================================================================

# ---------- 批 3 补充常量 ----------
#: character_states 里的数值型字段（写入时 clamp 到 0~1）
STATE_NUMERIC_FIELDS: Tuple[str, ...] = ("anger", "fear", "stress")
#: character_states 里的文本型字段
STATE_TEXT_FIELDS: Tuple[str, ...] = tuple(
    f for f in ALLOWED_STATE_FIELDS if f not in STATE_NUMERIC_FIELDS)
#: 提交承诺时必须截断的正文长度
COMMITMENT_CONTENT_MAX_LEN = 1000
SECRET_CONTENT_MAX_LEN = 1000
SECRET_SUBJECT_MAX_LEN = 256
RELATIONSHIP_SUMMARY_MAX_LEN = 1000
#: 承诺 overdue 判定：deadline 早于"现在"即视为过期
COMMITMENT_OVERDUE_STATUSES: Tuple[str, ...] = (COMMITMENT_ACTIVE, COMMITMENT_UNKNOWN)


# ==============================================================================
# 14. RelationshipManager —— 单向关系 + 历史
# ==============================================================================

class RelationshipManager:
    """``relationships`` 表的管理者。

    铁律：

    * **单向**：``from -> to`` 与 ``to -> from`` 是两条独立记录（SPEC 原则 9）
    * 数值字段只允许 ``ALLOWED_REL_FIELDS`` 里的 7 个
    * ``new_value = clamp(old + delta, 0.0, 1.0)``（强制校验 6）
    * 单次 ``|delta| > 0.5`` 直接拒绝（强制校验 7）—— 一次事件让信任 +0.9
      是模型发疯
    * 每次被接受的调整都写一行 ``relationship_history``，可追溯
    * ``character_states.trust / affection`` **不作为关系真相源**（强制校验 11）：
      本类只读写 ``relationships``
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
        llm: Optional["LLMClient"] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.logger = logger or _get_logger("relationships")
        # [P0] 仅用于首次从角色卡抽取初始关系；缺省 None 时该功能静默跳过
        self.llm = llm

    # ==================================================================
    # 内部
    # ==================================================================
    def _resolve(self, ref: Any) -> Optional[int]:
        if self.char_mgr is None:
            return _to_int(ref)
        return self.char_mgr.resolve_id(ref)

    @staticmethod
    def _validate_field(field_name: Any) -> Optional[str]:
        f = str(field_name or "").strip().lower()
        return f if f in ALLOWED_REL_FIELDS else None

    # ==================================================================
    # 读取
    # ==================================================================
    def get(self, from_c: Any, to_c: Any) -> Optional[Dict[str, Any]]:
        """取一条有向关系；不存在返回 None。"""
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return None
        return self.db.query_one(
            "SELECT * FROM relationships "
            "WHERE from_character_id = ? AND to_character_id = ?", (a, b))

    def get_or_create(self, from_c: Any, to_c: Any) -> Optional[Dict[str, Any]]:
        """取一条有向关系，不存在则按 schema 默认值新建。"""
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            self.logger.warning("[关系] 无法解析角色：%r -> %r", from_c, to_c)
            return None
        if a == b:
            self.logger.warning("[关系] 拒绝自指关系：%s", a)
            return None

        row = self.db.query_one(
            "SELECT * FROM relationships "
            "WHERE from_character_id = ? AND to_character_id = ?", (a, b))
        if row is not None:
            return row

        rid = self.db.insert(
            "INSERT INTO relationships "
            "(from_character_id, to_character_id, trust, affection, resentment, "
            " familiarity, respect, fear, dependency, state_summary, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
            (a, b, REL_DEFAULT_VALUES[REL_TRUST], REL_DEFAULT_VALUES[REL_AFFECTION],
             REL_DEFAULT_VALUES[REL_RESENTMENT], REL_DEFAULT_VALUES[REL_FAMILIARITY],
             REL_DEFAULT_VALUES[REL_RESPECT], REL_DEFAULT_VALUES[REL_FEAR],
             REL_DEFAULT_VALUES[REL_DEPENDENCY], now_iso()))
        if rid is None:
            # 并发插入：回查
            return self.db.query_one(
                "SELECT * FROM relationships "
                "WHERE from_character_id = ? AND to_character_id = ?", (a, b))
        self.logger.info("[关系] 新建 %s -> %s", a, b)
        return self.db.query_one(
            "SELECT * FROM relationships WHERE rel_id = ?", (int(rid),))

    def list_for(
        self,
        cid: Any,
        direction: str = "out",
    ) -> List[Dict[str, Any]]:
        """列出某角色的关系。

        ``direction``：``out``=该角色对别人的（默认）、``in``=别人对该角色的、
        ``both``=两者都算。
        """
        a = self._resolve(cid)
        if a is None:
            return []
        base = (
            "SELECT r.*, cf.name AS from_name, ct.name AS to_name "
            "FROM relationships r "
            "JOIN characters cf ON cf.character_id = r.from_character_id "
            "JOIN characters ct ON ct.character_id = r.to_character_id "
        )
        d = str(direction or "out").strip().lower()
        if d == "out":
            return self.db.query(
                base + "WHERE r.from_character_id = ? ORDER BY r.rel_id ASC", (a,))
        if d == "in":
            return self.db.query(
                base + "WHERE r.to_character_id = ? ORDER BY r.rel_id ASC", (a,))
        return self.db.query(
            base + "WHERE r.from_character_id = ? OR r.to_character_id = ? "
                   "ORDER BY r.rel_id ASC", (a, a))

    def all(self) -> List[Dict[str, Any]]:
        """全库关系（带双方名字），供 CLI / Web 展示。"""
        return self.db.query(
            "SELECT r.*, cf.name AS from_name, ct.name AS to_name "
            "FROM relationships r "
            "JOIN characters cf ON cf.character_id = r.from_character_id "
            "JOIN characters ct ON ct.character_id = r.to_character_id "
            "ORDER BY r.rel_id ASC")

    def count(self) -> int:
        """关系总条数（注意：单向，A->B 与 B->A 各算一条）。"""
        return self.db.count("relationships")

    # ==================================================================
    # 写入
    # ==================================================================
    def adjust(
        self,
        from_c: Any,
        to_c: Any,
        field_name: str,
        delta: float,
        reason: str = "",
        source_event_id: Optional[int] = None,
        source_belief_id: Optional[int] = None,
    ) -> bool:
        """按增量调整一个关系维度，返回是否成功。

        拒绝条件（都会 ``logging.warning``）：

        * ``field_name`` 不在 ``ALLOWED_REL_FIELDS`` 里
        * ``|delta| > 0.5``（强制校验 7）
        * ``delta`` 不是合法数字
        * 关系行创建失败

        成功时：``new = clamp(old + delta, 0, 1)``，并**必写一行**
        ``relationship_history``。
        """
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None or a == b:
            self.logger.warning("[关系] adjust 参数非法：%r -> %r", from_c, to_c)
            return False

        field = self._validate_field(field_name)
        if field is None:
            self.logger.warning(
                "[关系] 拒绝调整：非法字段 %r（必须是 %s 之一）",
                field_name, ALLOWED_REL_FIELDS)
            return False

        try:
            d = float(delta)
        except Exception:
            self.logger.warning("[关系] 拒绝调整：delta 不是数字 %r", delta)
            return False
        if d != d:  # NaN
            self.logger.warning("[关系] 拒绝调整：delta 为 NaN")
            return False
        if abs(d) > REL_MAX_DELTA:
            self.logger.warning(
                "[关系] 拒绝调整：单次 |delta|=%.3f 超过上限 %.1f"
                "（%s -> %s, 字段 %s）—— 单次事件不该造成如此大的变化",
                abs(d), REL_MAX_DELTA, a, b, field)
            return False

        row = self.get_or_create(a, b)
        if row is None:
            self.logger.warning("[关系] 调整失败：无法创建关系行 %s -> %s", a, b)
            return False

        old_value = _clamp(row.get(field), REL_MIN, REL_MAX,
                           REL_DEFAULT_VALUES.get(field, 0.5))
        new_value = max(REL_MIN, min(REL_MAX, old_value + d))
        now = now_iso()

        with self.db.transaction():
            cur = self.db.execute(
                f"UPDATE relationships SET {field} = ?, updated_at = ? "
                f"WHERE rel_id = ?",
                (new_value, now, int(row["rel_id"])))
            if cur is None:
                return False
            hist = self.db.execute(
                "INSERT INTO relationship_history "
                "(from_character_id, to_character_id, field, delta, old_value, "
                " new_value, reason, source_event_id, source_belief_id, changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (a, b, field, d, old_value, new_value,
                 _bounded_str(reason, RELATIONSHIP_SUMMARY_MAX_LEN) or None,
                 _to_int(source_event_id), _to_int(source_belief_id), now))
            if hist is None:
                self.logger.warning("[关系] 历史写入失败（主表已更新）")
        self.logger.info("[关系] %s -> %s %s: %.3f -> %.3f（Δ%+.3f）%s",
                         a, b, field, old_value, new_value, d,
                         f" 理由: {reason}" if reason else "")
        return True

    def set_value(
        self,
        from_c: Any,
        to_c: Any,
        field_name: str,
        value: float,
        reason: str = "",
        source_event_id: Optional[int] = None,
        source_belief_id: Optional[int] = None,
        enforce_delta_cap: bool = False,
    ) -> bool:
        """把某维度**绝对设定**为给定值，并写一行 ``relationship_history``。

        为什么不走 ``adjust``：SPEC 强制校验 7 的"``|delta| > 0.5`` 拒绝"
        明确限定于 **LLM 提出的 proposal**；本方法是 Python / CLI 层的显式
        设定（与 CLI 手工 ``add-visibility`` 默认 ``force=True`` 同理）。
        如果转发给 ``adjust``，``fear: 0.0 -> 0.7`` 这种合理的一次性设定
        也会被拦死。

        传 ``enforce_delta_cap=True`` 可以主动套用那道上限。

        无论哪条路径，**最终值一定会被 clamp 到 0.0~1.0**（强制校验 6）。
        """
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None or a == b:
            self.logger.warning("[关系] set_value 参数非法：%r -> %r", from_c, to_c)
            return False

        field = self._validate_field(field_name)
        if field is None:
            self.logger.warning("[关系] set_value 拒绝：非法字段 %r（必须是 %s 之一）",
                                field_name, ALLOWED_REL_FIELDS)
            return False

        try:
            target_raw = float(value)
        except Exception:
            self.logger.warning("[关系] set_value 拒绝：value 不是数字 %r", value)
            return False
        if target_raw != target_raw:  # NaN
            self.logger.warning("[关系] set_value 拒绝：value 为 NaN")
            return False

        row = self.get_or_create(a, b)
        if row is None:
            self.logger.warning("[关系] set_value 失败：无法创建关系行 %s -> %s", a, b)
            return False

        old_value = _clamp(row.get(field), REL_MIN, REL_MAX,
                           REL_DEFAULT_VALUES.get(field, 0.5))
        new_value = max(REL_MIN, min(REL_MAX, target_raw))

        if enforce_delta_cap and abs(new_value - old_value) > REL_MAX_DELTA:
            self.logger.warning(
                "[关系] set_value 拒绝：|Δ|=%.3f 超过上限 %.1f"
                "（%s -> %s, 字段 %s）",
                abs(new_value - old_value), REL_MAX_DELTA, a, b, field)
            return False

        now = now_iso()
        with self.db.transaction():
            cur = self.db.execute(
                f"UPDATE relationships SET {field} = ?, updated_at = ? "
                f"WHERE rel_id = ?",
                (new_value, now, int(row["rel_id"])))
            if cur is None:
                return False
            self.db.execute(
                "INSERT INTO relationship_history "
                "(from_character_id, to_character_id, field, delta, old_value, "
                " new_value, reason, source_event_id, source_belief_id, changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (a, b, field, new_value - old_value, old_value, new_value,
                 _bounded_str(reason, RELATIONSHIP_SUMMARY_MAX_LEN) or None,
                 _to_int(source_event_id), _to_int(source_belief_id), now))
        self.logger.info("[关系] set_value %s -> %s %s: %.3f -> %.3f",
                         a, b, field, old_value, new_value)
        return True

    # ==================================================================
    # [relations-7a] 怨恨（resentment）峰值 + 残留下限
    # ==================================================================
    def update_hate_peak(self, from_c: Any, to_c: Any) -> Optional[float]:
        """把 ``hate_peak`` 顶到当前 resentment 值（**只升不降**）。

        关系行不存在 / 字段异常时返回 None。
        """
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return None
        row = self.db.query_one(
            "SELECT rel_id, %s AS hate_v, hate_peak FROM relationships "
            "WHERE from_character_id = ? AND to_character_id = ?"
            % REL_HATE_FIELD, (a, b))
        if row is None:
            return None
        try:
            cur = _clamp(row.get("hate_v"), REL_MIN, REL_MAX, 0.0)
            peak = float(row.get("hate_peak") or 0.0)
        except Exception:
            return None
        if peak != peak:
            peak = 0.0
        new_peak = max(peak, cur)
        if new_peak > peak + 1e-9:
            self.db.execute(
                "UPDATE relationships SET hate_peak = ?, updated_at = ? "
                "WHERE rel_id = ?", (new_peak, now_iso(), int(row["rel_id"])))
            self.logger.info("[关系][hate] %s -> %s 峰值 %.3f -> %.3f",
                             a, b, peak, new_peak)
        return new_peak

    def apply_hate_floor(self, from_c: Any, to_c: Any) -> Optional[float]:
        """[relations-7a] 怨恨残留下限：``resentment >= hate_peak * ratio``。

        **在调用方执行**（不改 ``set_value`` / ``adjust`` 内部）。
        返回修正后的 resentment 值；无关系行返回 None。
        """
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return None
        peak = self.update_hate_peak(a, b)
        if peak is None:
            return None
        row = self.db.query_one(
            "SELECT rel_id, %s AS hate_v, hate_floor_ratio FROM relationships "
            "WHERE from_character_id = ? AND to_character_id = ?"
            % REL_HATE_FIELD, (a, b))
        if row is None:
            return None
        try:
            cur = _clamp(row.get("hate_v"), REL_MIN, REL_MAX, 0.0)
            ratio = float(row.get("hate_floor_ratio"))
        except Exception:
            ratio = HATE_DEFAULT_FLOOR_RATIO
        if ratio != ratio or ratio < 0.0:
            ratio = HATE_DEFAULT_FLOOR_RATIO
        new = max(cur, peak * ratio)
        new = max(REL_MIN, min(REL_MAX, new))
        if new > cur + 1e-9:
            now = now_iso()
            self.db.execute(
                "UPDATE relationships SET %s = ?, updated_at = ? "
                "WHERE rel_id = ?" % REL_HATE_FIELD,
                (new, now, int(row["rel_id"])))
            self.db.execute(
                "INSERT INTO relationship_history "
                "(from_character_id, to_character_id, field, delta, old_value, "
                " new_value, reason, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (a, b, REL_HATE_FIELD, new - cur, cur, new,
                 REL_HATE_FLOOR_REASON, now))
            self.logger.info(
                "[关系][hate] %s -> %s 残留下限 %.3f -> %.3f（peak=%.3f x %.2f）",
                a, b, cur, new, peak, ratio)
        return new

    # ==================================================================
    # [relations-9] 低置信度维度弱信号累积初始化
    # ==================================================================
    def _rel_unset_dims(self, a: int, b: int) -> List[str]:
        """[relations-9] 哪些维度 P0 没给过初始值。

        判据（**不加新列**）：``relationship_history`` 里有没有
        ``reason == REL_INIT_HISTORY_REASON`` 的行。
        """
        try:
            rows = self.db.query(
                "SELECT DISTINCT field FROM relationship_history "
                "WHERE from_character_id = ? AND to_character_id = ? "
                "AND reason = ?", (a, b, REL_INIT_HISTORY_REASON))
        except Exception:
            return []
        got = set()
        for r in (rows or []):
            if r.get("field"):
                got.add(str(r.get("field")))
        return [f for f in ALLOWED_REL_FIELDS if f not in got]

    def note_weak_signal(self, from_c: Any, to_c: Any,
                         field_name: Any, delta: Any) -> Optional[float]:
        """[relations-9] 记一次弱信号。

        同向累积满 ``REL_WEAK_SIGNAL_COUNT`` 次 -> 初始化该维度
        （值 = 默认值 + 累积平均值）；方向相反 -> 清空该维度累积。
        状态存内存，重启即丢。返回初始化后的值，否则 None。
        """
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return None
        fld = self._validate_field(field_name)
        if fld is None:
            return None
        try:
            d = float(delta)
        except Exception:
            return None
        if d != d or abs(d) < 1e-9:
            return None
        try:
            with _rel_pending_lock:
                unset = _rel_unset_cache.get((a, b))
            if unset is None:
                unset = set(self._rel_unset_dims(a, b))
                with _rel_pending_lock:
                    _rel_unset_cache[(a, b)] = unset
            if fld not in unset:
                return None
            key = (a, b, fld)
            with _rel_pending_lock:
                cur = list(_rel_pending_signals.get(key) or [])
            if cur and (cur[0] > 0) != (d > 0):
                with _rel_pending_lock:
                    _rel_pending_signals.pop(key, None)
                self.logger.info(
                    "[关系][弱信号] %s -> %s %s 方向反转，清空累积", a, b, fld)
                return None
            cur.append(d)
            if len(cur) < REL_WEAK_SIGNAL_COUNT:
                with _rel_pending_lock:
                    _rel_pending_signals[key] = cur
                self.logger.info(
                    "[关系][弱信号] %s -> %s %s 累积 %d/%d",
                    a, b, fld, len(cur), REL_WEAK_SIGNAL_COUNT)
                return None
            with _rel_pending_lock:
                _rel_pending_signals.pop(key, None)
            base = REL_DEFAULT_VALUES.get(fld, 0.5)
            val = max(REL_MIN, min(REL_MAX, base + sum(cur) / float(len(cur))))
            if self.set_value(a, b, fld, val, reason=REL_WEAK_INIT_REASON):
                with _rel_pending_lock:
                    _rel_unset_cache.pop((a, b), None)
                self.logger.info(
                    "[关系][弱信号] %s -> %s %s 累积满 %d 次，初始化为 %.3f",
                    a, b, fld, REL_WEAK_SIGNAL_COUNT, val)
                return val
            return None
        except Exception as ex:
            self.logger.warning("[关系][弱信号] 处理失败（忽略）：%s", ex)
            return None

    def set_summary(self, from_c: Any, to_c: Any, summary: str) -> bool:
        """写一段关系自然语言摘要（``state_summary``）。"""
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return False
        row = self.get_or_create(a, b)
        if row is None:
            return False
        cur = self.db.execute(
            "UPDATE relationships SET state_summary = ?, updated_at = ? "
            "WHERE rel_id = ?",
            (_bounded_str(summary, RELATIONSHIP_SUMMARY_MAX_LEN) or None,
             now_iso(), int(row["rel_id"])))
        return cur is not None

    def history(
        self,
        from_c: Any,
        to_c: Any,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """取两个角色之间的关系变更历史（新 -> 旧）。"""
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return []
        sql = ("SELECT * FROM relationship_history "
               "WHERE from_character_id = ? AND to_character_id = ? "
               "ORDER BY changed_at DESC, id DESC")
        params: List[Any] = [a, b]
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    # ==================================================================
    # [P0] 初始关系：从角色卡设定文本抽取
    # ==================================================================
    def needs_init(self, from_c: Any, to_c: Any) -> bool:
        """[P0] 该关系行是否需要初始化（行不存在 或 initialized=0）。"""
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return False
        row = self.db.query_one(
            "SELECT initialized FROM relationships "
            "WHERE from_character_id = ? AND to_character_id = ?", (a, b))
        if row is None:
            return True
        return _to_int(row.get("initialized")) != 1

    def mark_initialized(self, from_c: Any, to_c: Any) -> bool:
        """[P0] 标记已初始化。成功 / 失败 / 无卡文本都要标记，避免每轮重试。"""
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            return False
        cur = self.db.execute(
            "UPDATE relationships SET initialized = 1 "
            "WHERE from_character_id = ? AND to_character_id = ?", (a, b))
        return cur is not None

    def initialize_from_card(self, from_c: Any, to_c: Any,
                             persona_text: str) -> bool:
        """[P0] 首次建关系行时调用：调一次 LLM 从卡文本抽 7 维初始值。

        **调用方必须保证不在事务里**（中继路径无事务，安全）。
        返回 True = 成功写入；False = 失败，保持默认值。
        """
        a, b = self._resolve(from_c), self._resolve(to_c)
        if a is None or b is None:
            self.logger.warning("[关系][P0] 无法解析角色：%r -> %r",
                                from_c, to_c)
            return False
        text = str(persona_text or "").strip()
        if not text:
            self.logger.warning("[关系][P0] 卡里无关系信息（卡文本为空），保持默认")
            return False
        if self.llm is None or not bool(getattr(self.llm, "enabled", False)):
            self.logger.warning("[关系][P0] LLM 未启用，保持默认值")
            return False
        row = self.db.query_one(
            "SELECT * FROM relationships "
            "WHERE from_character_id = ? AND to_character_id = ?", (a, b))
        if row is None:
            self.logger.warning("[关系][P0] 关系行不存在（%s -> %s）", a, b)
            return False

        # 角色名 = from_c（卡描述的是"拥有这条关系"的那一方）
        _cr = self.char_mgr.get(a) if self.char_mgr is not None else None
        from_name = str((_cr or {}).get("name") or a)
        user = "角色名：%s\n角色设定文本：%s" % (
            from_name, text[:REL_INIT_PERSONA_MAX_LEN])
        try:
            data = self.llm.chat_json(REL_INIT_SYSTEM_PROMPT, user)
        except Exception as ex:
            self.logger.warning("[关系][P0] LLM 调用异常，保持默认值：%s", ex)
            return False
        if not isinstance(data, dict):
            self.logger.warning("[关系][P0] LLM 未返回合法 JSON，保持默认值")
            return False

        picked: Dict[str, float] = {}
        skipped: List[str] = []
        for key, field in REL_INIT_FIELD_MAP:
            item = data.get(key)
            if not isinstance(item, dict) or field not in ALLOWED_REL_FIELDS:
                skipped.append(key)
                continue
            conf = str(item.get("confidence") or "").strip().lower()
            val = item.get("value")
            if conf not in REL_INIT_VALID_CONF or conf in REL_INIT_SKIP_CONF:
                skipped.append(key)
                continue
            if val is None or isinstance(val, bool):
                skipped.append(key)
                continue
            try:
                fv = float(val)
            except Exception:
                skipped.append(key)
                continue
            if fv != fv:
                skipped.append(key)
                continue
            picked[field] = _clamp(fv, REL_MIN, REL_MAX,
                                   REL_DEFAULT_VALUES[field])

        if not picked:
            self.logger.warning(
                "[关系][P0] 卡里无关系信息，保持默认（7 维全 low/unset）")
            return False

        now = now_iso()
        for field, val in picked.items():
            old = _clamp(row.get(field), REL_MIN, REL_MAX,
                         REL_DEFAULT_VALUES[field])
            self.db.execute(
                "UPDATE relationships SET %s = ?, updated_at = ? "
                "WHERE from_character_id = ? AND to_character_id = ?"
                % field, (val, now, a, b))
            self.db.execute(
                "INSERT INTO relationship_history "
                "(from_character_id, to_character_id, field, delta, "
                " old_value, new_value, reason, changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (a, b, field, val - old, old, val,
                 REL_INIT_HISTORY_REASON, now))
        self.mark_initialized(a, b)
        self.logger.info(
            "[关系][P0] 初始关系已写入 %s -> %s：%d 维来自角色卡（%s）；"
            "跳过 %d 维（%s）",
            a, b, len(picked),
            ", ".join("%s=%.2f" % (f, v) for f, v in sorted(picked.items())),
            len(skipped), ", ".join(skipped) or "-")
        return True

    # ==================================================================
    # [元指令] 手动关系推进（玩家在对话里插入的"给系统的指令"）
    # ==================================================================
    def _resolve_meta_party(self, name: str,
                            user_id: Optional[int]) -> Optional[int]:
        """[元指令] 把 '用户' / 角色名 解析成 character_id。"""
        key = str(name or "").strip()
        if not key:
            return None
        if key.lower() in META_CMD_USER_ALIASES and user_id is not None:
            return user_id
        return self._resolve(key)

    def detect_meta_command(self, user_text: str,
                            character: str = "") -> Dict[str, Any]:
        """[元指令] 判断用户消息是不是给系统的元指令（非角色对话）。

        返回 ``{"is_meta": bool, "confidence": float, "changes": [...]}``。
        任何失败都返回 ``{"is_meta": False}``（并打 WARNING），绝不抛异常。
        """
        text = str(user_text or "").strip()
        if not text:
            return {"is_meta": False}
        if self.llm is None or not bool(getattr(self.llm, "enabled", False)):
            return {"is_meta": False}
        # [元指令] 带上当前场景角色；否则 LLM 只能靠正文猜 from/to
        _scene = str(character or "").strip()
        payload = ("当前场景角色：%s\n%s" % (_scene, text)) if _scene else text
        try:
            data = self.llm.chat_json(META_CMD_SYSTEM_PROMPT, payload)
        except Exception as ex:
            self.logger.warning("[元指令] LLM 调用异常：%s", ex)
            return {"is_meta": False}
        if not isinstance(data, dict):
            self.logger.warning("[元指令] LLM 未返回合法 JSON")
            return {"is_meta": False}
        try:
            conf = float(data.get("confidence"))
        except Exception:
            conf = 0.0
        if conf != conf:
            conf = 0.0
        changes = data.get("changes")
        if not isinstance(changes, list):
            changes = []
        return {
            "is_meta": bool(data.get("is_meta")),
            "confidence": conf,
            "changes": changes,
        }

    def apply_meta_command(self, changes: Any) -> int:
        """[元指令] 把识别出的 changes 落地。

        走 ``set_value``（Python 层显式设定），因而**不受** ``adjust`` 的
        ``|delta| > 0.5`` 上限约束。返回成功执行条数。
        """
        if not isinstance(changes, (list, tuple)):
            return 0
        user_row = (self.char_mgr.get_user()
                    if self.char_mgr is not None else None)
        uid = _to_int(user_row.get("character_id")) if user_row else None
        done = 0
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            raw_from = str(ch.get("from") or "").strip()
            raw_to = str(ch.get("to") or "").strip()
            a = self._resolve_meta_party(raw_from, uid)
            b = self._resolve_meta_party(raw_to, uid)
            if a is None or b is None or a == b:
                self.logger.warning("[元指令] 跳过：无法解析 %r -> %r（%s -> %s）",
                                    raw_from, raw_to, a, b)
                continue
            dim = str(ch.get("dimension") or "").strip().lower()
            field = META_DIM_SYNONYMS.get(dim)
            if field is None or field not in ALLOWED_REL_FIELDS:
                self.logger.warning("[元指令] 跳过：未知 dimension %r", dim)
                continue
            lvl = str(ch.get("target_level") or "").strip().lower()
            if lvl not in META_LEVEL_VALUES:
                self.logger.warning("[元指令] 跳过：未知 target_level %r", lvl)
                continue
            val = META_LEVEL_VALUES[lvl]
            reason = str(ch.get("reason") or "")[:META_CMD_REASON_MAX_LEN]
            if self.set_value(a, b, field, val, reason=reason,
                              source_event_id=None):
                done += 1
                try:
                    self.apply_hate_floor(a, b)
                except Exception as ex:
                    self.logger.warning(
                        "[元指令][hate] 峰值/下限失败（忽略）：%s", ex)
                self.logger.info(
                    "[元指令] %s → %s %s 设为 %.2f（%s），原因：%s",
                    raw_from or a, raw_to or b, field, val, lvl, reason)
        return done

    def get_recent_history(
        self,
        char_a: Any,
        char_b: Any,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """[relations-2] 取 A→B 最近 N 条关系变更记录（新 -> 旧）。

        供 ContextBuilder 生成"关系证据"短句用。命中现成索引
        ``idx_relh_pair(from_character_id, to_character_id, changed_at)``。
        """
        a, b = self._resolve(char_a), self._resolve(char_b)
        if a is None or b is None:
            return []
        try:
            lim = max(1, int(limit or 1))
        except Exception:
            lim = 3
        return self.db.query(
            "SELECT * FROM relationship_history "
            "WHERE from_character_id = ? AND to_character_id = ? "
            "ORDER BY changed_at DESC, id DESC LIMIT ?",
            (a, b, lim))

    def describe(self, from_c: Any, to_c: Any) -> str:
        """把一条关系压成一句中文摘要（供 ContextBuilder / CLI 用）。"""
        row = self.get(from_c, to_c)
        if row is None:
            return "（无记录）"
        if row.get("state_summary"):
            return str(row["state_summary"])

        positives = [(REL_TRUST, "信任"), (REL_AFFECTION, "好感"),
                     (REL_RESPECT, "敬重"), (REL_FAMILIARITY, "熟悉"),
                     (REL_DEPENDENCY, "依赖")]
        negatives = [(REL_RESENTMENT, "怨恨"), (REL_FEAR, "畏惧")]
        parts: List[str] = []
        for f, label in positives:
            v = _clamp(row.get(f), 0.0, 1.0, 0.5)
            if v >= 0.65:
                parts.append(f"{label}高({v:.2f})")
            elif v <= 0.30:
                parts.append(f"{label}低({v:.2f})")
        for f, label in negatives:
            v = _clamp(row.get(f), 0.0, 1.0, 0.0)
            if v >= 0.40:
                parts.append(f"{label}重({v:.2f})")
        if not parts:
            return "关系平淡，无明显倾向"
        return "；".join(parts)


# ==============================================================================
# 15. StateManager —— 角色状态 + 历史
# ==============================================================================

class StateManager:
    """``character_states`` 表的管理者 —— **只表达角色自身的当前状态**。

    ``character_states`` 是固定 14 列的表（不是键值表），因此 ``set_field``
    的 ``field_name`` 必须在 ``ALLOWED_STATE_FIELDS`` 里，代码用白名单把列名
    拼进 SQL（值仍然参数化）。

    **``trust`` / ``affection`` 两个列是兼容旧版字段，不作为"对某人的关系"的
    真相源**（SPEC 原则 10 / 强制校验 11）：

    * 所有对他人的 trust / affection 必须以 ``relationships`` 表为准
    * 默认情况下 ``set_field`` **拒绝**写这两个字段，并提示改用
      ``RelationshipManager``；只有明确导入旧数据时才传
      ``allow_compat=True``
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.logger = logger or _get_logger("states")

    # ------------------------------------------------------------------
    def _resolve(self, cid: Any) -> Optional[int]:
        if self.char_mgr is None:
            return _to_int(cid)
        return self.char_mgr.resolve_id(cid)

    @staticmethod
    def _validate_field(field_name: Any) -> Optional[str]:
        f = str(field_name or "").strip().lower()
        return f if f in ALLOWED_STATE_FIELDS else None

    # ------------------------------------------------------------------
    def ensure(self, cid: Any) -> Optional[int]:
        """确保角色有状态行，返回 character_id。"""
        c = self._resolve(cid)
        if c is None:
            return None
        if self.db.query_one(
                "SELECT character_id FROM character_states WHERE character_id = ?",
                (c,)) is None:
            self.db.execute(
                "INSERT INTO character_states(character_id, updated_at) "
                "VALUES (?, ?)", (c, now_iso()))
        return c

    def get(self, cid: Any) -> Optional[Dict[str, Any]]:
        """取角色当前状态；无记录返回 None。"""
        c = self._resolve(cid)
        if c is None:
            return None
        return self.db.query_one(
            "SELECT * FROM character_states WHERE character_id = ?", (c,))

    def get_field(self, cid: Any, field_name: str) -> Any:
        """取单个状态字段的值。"""
        row = self.get(cid)
        if row is None:
            return None
        f = str(field_name or "").strip().lower()
        return row.get(f) if f in (ALLOWED_STATE_FIELDS + STATE_COMPAT_FIELDS) else None

    def set_field(
        self,
        cid: Any,
        field_name: str,
        value: Any,
        reason: str = "",
        source_event_id: Optional[int] = None,
        allow_compat: bool = False,
    ) -> bool:
        """设置一个状态字段，并写一行 ``state_history``；成功返回 True。

        数值型字段（anger / fear / stress）会 clamp 到 0~1；
        其余按字符串存储（上限 ``STATE_VALUE_MAX_LEN``）。

        ``trust`` / ``affection`` 属兼容字段，默认**拒绝**写入
        （见类文档：关系真相源是 ``relationships``）。
        """
        c = self._resolve(cid)
        if c is None:
            self.logger.warning("[状态] 拒绝写入：角色 %r 无法解析", cid)
            return False

        f = str(field_name or "").strip().lower()
        if f in STATE_COMPAT_FIELDS:
            if not allow_compat:
                self.logger.warning(
                    "[状态] 拒绝写入 character_states.%s：该字段仅为兼容旧版保留，"
                    "不作为关系真相源 —— 请改用 RelationshipManager", f)
                return False
        elif f not in ALLOWED_STATE_FIELDS:
            self.logger.warning(
                "[状态] 拒绝写入：非法字段 %r（允许：%s，兼容：%s）",
                field_name, ALLOWED_STATE_FIELDS, STATE_COMPAT_FIELDS)
            return False

        if self.ensure(c) is None:
            return False
        row = self.get(c) or {}
        old_value = row.get(f)

        if f in STATE_NUMERIC_FIELDS or f in STATE_COMPAT_FIELDS:
            # 注意：必须先自己做 float() 校验。不能直接丢给 _clamp ——
            # _clamp 内部会把转换失败吞掉并返回默认值，导致 "很怕" 这类
            # 非法输入被静默写成默认值还报成功。
            try:
                num = float(value)
            except Exception:
                self.logger.warning("[状态] 拒绝写入：%s 需要数值，收到 %r", f, value)
                return False
            if num != num:  # NaN
                self.logger.warning("[状态] 拒绝写入：%s 不接受 NaN", f)
                return False
            new_value: Any = _clamp(num, 0.0, 1.0, 0.0)
        else:
            new_value = _bounded_str(value, STATE_VALUE_MAX_LEN) or None

        if old_value == new_value:
            if new_value is None:
                self.logger.warning(
                    "[状态] 拒绝写入：字段 %s 的值被截断后为空且原值为空（无需改动）", f)
                return False

        now = now_iso()
        with self.db.transaction():
            cur = self.db.execute(
                f"UPDATE character_states SET {f} = ?, updated_at = ? "
                f"WHERE character_id = ?",
                (new_value, now, c))
            if cur is None:
                return False
            self.db.execute(
                "INSERT INTO state_history "
                "(character_id, field, old_value, new_value, reason, "
                " source_event_id, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (c, f,
                 None if old_value is None else str(old_value),
                 None if new_value is None else str(new_value),
                 _bounded_str(reason, RELATIONSHIP_SUMMARY_MAX_LEN) or None,
                 _to_int(source_event_id), now))
        self.logger.debug("[状态] 角色 %s 的 %s: %r -> %r", c, f, old_value, new_value)
        return True

    def set_fields(
        self,
        cid: Any,
        values: Dict[str, Any],
        reason: str = "",
        source_event_id: Optional[int] = None,
        allow_compat: bool = False,
    ) -> int:
        """批量设置多个状态字段，返回成功条数。"""
        n = 0
        for f, v in (values or {}).items():
            if self.set_field(cid, f, v, reason, source_event_id, allow_compat):
                n += 1
        return n

    def history(
        self,
        cid: Any,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """取状态变更历史（新 -> 旧）。"""
        c = self._resolve(cid)
        if c is None:
            return []
        sql = ("SELECT * FROM state_history WHERE character_id = ? "
               "ORDER BY changed_at DESC, id DESC")
        params: List[Any] = [c]
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def list_all(self) -> List[Dict[str, Any]]:
        """全部角色的状态（带名字）。"""
        return self.db.query(
            "SELECT s.*, c.name AS character_name, c.role_type "
            "FROM character_states s "
            "JOIN characters c ON c.character_id = s.character_id "
            "ORDER BY c.character_id ASC")

    def count(self) -> int:
        """有状态记录的角色数。"""
        return self.db.count("character_states")

    def describe(self, cid: Any) -> str:
        """把状态压成一句中文摘要。"""
        row = self.get(cid)
        if row is None:
            return "（无状态记录）"
        if row.get("summary"):
            return str(row["summary"])
        bits: List[str] = []
        for f in ("emotion", "mood", "current_location", "current_goal"):
            if row.get(f):
                bits.append(f"{f}={row[f]}")
        for f in ("anger", "fear", "stress"):
            v = _clamp(row.get(f), 0.0, 1.0, 0.0)
            if v > 0.01:
                bits.append(f"{f}={v:.2f}")
        return "；".join(bits) if bits else "（状态平淡）"


# ==============================================================================
# 16. CommitmentManager —— 承诺
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【12】承诺 + 秘密
# ══════════════════════════════════════════════════════════════════════

class CommitmentManager:
    """``commitments`` 表的管理者。

    * ``promiser_id`` 必填，``promisee_id`` 可空（无明确对象的承诺）
    * ``status`` ∈ {active, fulfilled, broken, expired, unknown}
    * ``deadline`` 存 ISO-8601 字符串，可为空
    * 同一 ``(promiser, promisee, content)`` 去重，避免重复导入产生重复承诺
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.logger = logger or _get_logger("commitments")

    # ------------------------------------------------------------------
    def _resolve(self, ref: Any) -> Optional[int]:
        if ref is None:
            return None
        if self.char_mgr is None:
            return _to_int(ref)
        return self.char_mgr.resolve_id(ref)

    @staticmethod
    def _dedup_hash(promiser_id: int, promisee_id: Optional[int],
                    content: str) -> str:
        return _sha(f"com|{promiser_id}|{promisee_id or 0}|"
                    f"{_WS_RE.sub('', content or '')}")

    # ------------------------------------------------------------------
    def add(
        self,
        promiser: Any,
        promisee: Any = None,
        content: str = "",
        deadline: Optional[str] = None,
        source_event_id: Optional[int] = None,
        notes: str = "",
        status: str = COMMITMENT_ACTIVE,
    ) -> Optional[int]:
        """登记一条承诺，返回 ``commitment_id``（失败/重复返回已有 id 或 None）。"""
        pid = self._resolve(promiser)
        if pid is None:
            self.logger.warning("[承诺] 拒绝写入：承诺者 %r 无法解析", promiser)
            return None

        text = _bounded_str(content, COMMITMENT_CONTENT_MAX_LEN)
        if not text:
            self.logger.warning("[承诺] 拒绝写入：content 为空（承诺者=%s）", pid)
            return None

        ppid = self._resolve(promisee) if promisee is not None else None
        if promisee is not None and ppid is None:
            self.logger.info("[承诺] 受诺者 %r 无法解析，按『无明确对象』记录", promisee)

        st = str(status or COMMITMENT_ACTIVE).strip().lower()
        if st not in VALID_COMMITMENT_STATUSES:
            self.logger.warning("[承诺] 拒绝写入：非法 status %r（应为 %s）",
                                status, VALID_COMMITMENT_STATUSES)
            return None

        dl = _norm_iso(deadline, None) if deadline else None
        if deadline and dl is None:
            self.logger.warning("[承诺] deadline %r 无法解析为时间，已置空", deadline)

        ev_id = _to_int(source_event_id)
        if ev_id is not None and self.db.query_one(
                "SELECT event_id FROM events WHERE event_id = ?", (ev_id,)) is None:
            self.logger.warning("[承诺] 拒绝写入：source_event_id=%s 不存在", ev_id)
            return None

        dh = self._dedup_hash(pid, ppid, text)
        existing = self.db.query_one(
            "SELECT commitment_id FROM commitments WHERE dedup_hash = ? LIMIT 1",
            (dh,))
        if existing is not None:
            self.logger.debug("[承诺] 已存在同内容承诺，复用 id=%s",
                              existing["commitment_id"])
            return int(existing["commitment_id"])

        cid_new = self.db.insert(
            "INSERT INTO commitments "
            "(promiser_id, promisee_id, content, created_at, deadline, status, "
            " source_event_id, notes, dedup_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, ppid, text, now_iso(), dl, st, ev_id,
             _bounded_str(notes, COMMITMENT_CONTENT_MAX_LEN) or None, dh))
        if cid_new is None:
            return None
        self.logger.info("[承诺] 新建 id=%s %s -> %s 期限=%s 正文=%s",
                         cid_new, pid, ppid if ppid else "（无对象）",
                         dl or "无", text[:30])
        return int(cid_new)

    # ------------------------------------------------------------------
    def get(self, commitment_id: Any) -> Optional[Dict[str, Any]]:
        """按 id 取承诺（附双方名字）。"""
        k = _to_int(commitment_id)
        if k is None:
            return None
        return self.db.query_one(
            "SELECT cm.*, cp.name AS promiser_name, ce.name AS promisee_name "
            "FROM commitments cm "
            "LEFT JOIN characters cp ON cp.character_id = cm.promiser_id "
            "LEFT JOIN characters ce ON ce.character_id = cm.promisee_id "
            "WHERE cm.commitment_id = ?", (k,))

    def _query(
        self,
        where: str,
        params: Sequence[Any],
        statuses: Optional[Sequence[str]],
        limit: Optional[int] = None,
        order: str = "COALESCE(cm.deadline, '9999') ASC, cm.commitment_id DESC",
    ) -> List[Dict[str, Any]]:
        sql = (
            "SELECT cm.*, cp.name AS promiser_name, ce.name AS promisee_name "
            "FROM commitments cm "
            "LEFT JOIN characters cp ON cp.character_id = cm.promiser_id "
            "LEFT JOIN characters ce ON ce.character_id = cm.promisee_id "
            f"WHERE {where}"
        )
        out_params: List[Any] = list(params)
        if statuses:
            sl = [str(s).strip().lower() for s in statuses]
            bad = [s for s in sl if s not in VALID_COMMITMENT_STATUSES]
            if bad:
                self.logger.warning("[承诺] 忽略非法 status：%s", bad)
            sl = [s for s in sl if s in VALID_COMMITMENT_STATUSES]
            if not sl:
                return []
            marks = ", ".join("?" * len(sl))
            sql += f" AND cm.status IN ({marks})"
            out_params.extend(sl)
        sql += f" ORDER BY {order}"
        if limit:
            sql += " LIMIT ?"
            out_params.append(int(limit))
        return self.db.query(sql, tuple(out_params))

    def list_for_character(
        self,
        cid: Any,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """该角色相关的承诺（**既是承诺者也是受诺者**）。"""
        c = self._resolve(cid)
        if c is None:
            return []
        return self._query("(cm.promiser_id = ? OR cm.promisee_id = ?)",
                           [c, c], statuses)

    def list_by_promiser(
        self,
        cid: Any,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """该角色**做出**的承诺。"""
        c = self._resolve(cid)
        if c is None:
            return []
        return self._query("cm.promiser_id = ?", [c], statuses)

    def list_by_promisee(
        self,
        cid: Any,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """别人**对该角色**做出的承诺。"""
        c = self._resolve(cid)
        if c is None:
            return []
        return self._query("cm.promisee_id = ?", [c], statuses)

    def list_between(
        self,
        cid_a: Any,
        cid_b: Any,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """两个角色之间（双向）的承诺 —— 供 ContextBuilder / Stance 使用。"""
        a, b = self._resolve(cid_a), self._resolve(cid_b)
        if a is None or b is None:
            return []
        return self._query(
            "((cm.promiser_id = ? AND cm.promisee_id = ?) "
            " OR (cm.promiser_id = ? AND cm.promisee_id = ?))",
            [a, b, b, a], statuses)

    def all(self, statuses: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        """全库承诺。"""
        return self._query("1 = 1", [], statuses)

    # ------------------------------------------------------------------
    def set_status(self, commitment_id: Any, status: str) -> bool:
        """变更承诺状态。"""
        k = _to_int(commitment_id)
        if k is None:
            return False
        st = str(status or "").strip().lower()
        if st not in VALID_COMMITMENT_STATUSES:
            self.logger.warning("[承诺] set_status 非法 status %r（应为 %s）",
                                status, VALID_COMMITMENT_STATUSES)
            return False
        if self.get(k) is None:
            self.logger.warning("[承诺] set_status 失败：%s 不存在", k)
            return False
        cur = self.db.execute(
            "UPDATE commitments SET status = ? WHERE commitment_id = ?", (st, k))
        if cur is not None:
            self.logger.info("[承诺] id=%s 状态 -> %s", k, st)
        return cur is not None

    def check_overdue(
        self,
        mark_expired: bool = True,
        now: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """找出已过期（``deadline`` 早于当前时间）且仍未完结的承诺。

        ``mark_expired=True``（默认）时顺手把它们的 ``status`` 流转为
        ``'expired'``；传 ``False`` 则只读不改，适合干跑检查。
        """
        ref = _norm_iso(now, now_iso())
        rows = self._query(
            "cm.deadline IS NOT NULL AND cm.deadline != '' AND cm.deadline < ?",
            [ref], list(COMMITMENT_OVERDUE_STATUSES))
        if rows and mark_expired:
            ids = [int(r["commitment_id"]) for r in rows]
            marks = ", ".join("?" * len(ids))
            cur = self.db.execute(
                f"UPDATE commitments SET status = ? "
                f"WHERE commitment_id IN ({marks})",
                tuple([COMMITMENT_EXPIRED] + ids))
            if cur is not None:
                self.logger.info("[承诺] %d 条过期承诺已流转为 expired", len(ids))
        return rows

    def count(self, statuses: Optional[Sequence[str]] = None) -> int:
        """承诺条数。"""
        if not statuses:
            return self.db.count("commitments")
        sl = [s for s in (str(x).strip().lower() for x in statuses)
              if s in VALID_COMMITMENT_STATUSES]
        if not sl:
            return 0
        marks = ", ".join("?" * len(sl))
        return int(self.db.scalar(
            f"SELECT COUNT(*) FROM commitments WHERE status IN ({marks})",
            tuple(sl), 0) or 0)


# ==============================================================================
# 17. SecretManager —— 秘密
# ==============================================================================

class SecretManager:
    """``secrets`` 表的管理者。

    * 秘密属于 ``owner_character_id``（**保守秘密的人**）
    * ``revealed_to`` 是 JSON 数组，存**已经知情**的 character_id
    * ``status`` ∈ {active, revealed, obsolete}；``active`` = 仍在保密
    * 泄漏是单向累积的：``reveal_to`` 只追加，不撤回
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.logger = logger or _get_logger("secrets")

    # ------------------------------------------------------------------
    def _resolve(self, ref: Any) -> Optional[int]:
        if ref is None:
            return None
        if self.char_mgr is None:
            return _to_int(ref)
        return self.char_mgr.resolve_id(ref)

    @staticmethod
    def _dedup_hash(owner_id: int, content: str) -> str:
        return _sha(f"sec|{owner_id}|{_WS_RE.sub('', content or '')}")

    # ------------------------------------------------------------------
    def add(
        self,
        owner: Any,
        content: str,
        subject: str = "",
        source_event_id: Optional[int] = None,
        status: str = SECRET_ACTIVE,
    ) -> Optional[int]:
        """登记一条秘密，返回 ``secret_id``。"""
        oid = self._resolve(owner)
        if oid is None:
            self.logger.warning("[秘密] 拒绝写入：owner %r 无法解析", owner)
            return None

        text = _bounded_str(content, SECRET_CONTENT_MAX_LEN)
        if not text:
            self.logger.warning("[秘密] 拒绝写入：content 为空（owner=%s）", oid)
            return None

        st = str(status or SECRET_ACTIVE).strip().lower()
        if st not in VALID_SECRET_STATUSES:
            self.logger.warning("[秘密] 拒绝写入：非法 status %r（应为 %s）",
                                status, VALID_SECRET_STATUSES)
            return None

        ev_id = _to_int(source_event_id)
        if ev_id is not None and self.db.query_one(
                "SELECT event_id FROM events WHERE event_id = ?", (ev_id,)) is None:
            self.logger.warning("[秘密] 拒绝写入：source_event_id=%s 不存在", ev_id)
            return None

        dh = self._dedup_hash(oid, text)
        existing = self.db.query_one(
            "SELECT secret_id FROM secrets WHERE dedup_hash = ? LIMIT 1", (dh,))
        if existing is not None:
            self.logger.debug("[秘密] 已存在同内容秘密，复用 id=%s",
                              existing["secret_id"])
            return int(existing["secret_id"])

        sid = self.db.insert(
            "INSERT INTO secrets "
            "(owner_character_id, content, subject, revealed_to, status, "
            " source_event_id, created_at, dedup_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, text, _bounded_str(subject, SECRET_SUBJECT_MAX_LEN) or None,
             EMPTY_JSON_ARRAY, st, ev_id, now_iso(), dh))
        if sid is None:
            return None
        self.logger.info("[秘密] 新建 id=%s owner=%s subject=%s",
                         sid, oid, subject or "-")
        return int(sid)

    # ------------------------------------------------------------------
    def get_secret(self, secret_id: Any) -> Optional[Dict[str, Any]]:
        """按 id 取秘密（附 owner 名字）。"""
        sid = _to_int(secret_id)
        if sid is None:
            return None
        return self.db.query_one(
            "SELECT s.*, c.name AS owner_name FROM secrets s "
            "LEFT JOIN characters c ON c.character_id = s.owner_character_id "
            "WHERE s.secret_id = ?", (sid,))

    def list_for(
        self,
        cid: Any,
        statuses: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """该角色**自己持有**的秘密。"""
        oid = self._resolve(cid)
        if oid is None:
            return []
        sql = ("SELECT s.*, c.name AS owner_name FROM secrets s "
               "LEFT JOIN characters c ON c.character_id = s.owner_character_id "
               "WHERE s.owner_character_id = ?")
        params: List[Any] = [oid]
        if statuses:
            sl = [s for s in (str(x).strip().lower() for x in statuses)
                  if s in VALID_SECRET_STATUSES]
            if sl:
                marks = ", ".join("?" * len(sl))
                sql += f" AND s.status IN ({marks})"
                params.extend(sl)
        sql += " ORDER BY s.secret_id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def list_active(self, cid: Any) -> List[Dict[str, Any]]:
        """该角色仍在保密中的秘密。"""
        return self.list_for(cid, statuses=[SECRET_ACTIVE])

    # ------------------------------------------------------------------
    def reveal_to(self, secret_id: Any, target: Any) -> bool:
        """把秘密告知某人：把 target 的 character_id 追加进 ``revealed_to``。

        只追加不撤回；重复告知同一人是幂等的。
        """
        sid = _to_int(secret_id)
        if sid is None:
            return False
        secret = self.db.query_one(
            "SELECT secret_id, owner_character_id, revealed_to FROM secrets "
            "WHERE secret_id = ?", (sid,))
        if secret is None:
            self.logger.warning("[秘密] reveal_to 失败：%s 不存在", sid)
            return False

        tid = self._resolve(target)
        if tid is None:
            self.logger.warning("[秘密] reveal_to 失败：目标 %r 无法解析", target)
            return False
        if int(tid) == int(secret["owner_character_id"]):
            self.logger.warning("[秘密] reveal_to 失败：%s 就是秘密持有者自己", tid)
            return False

        current: List[int] = []
        for x in _as_list(secret.get("revealed_to")):
            xi = _to_int(x)
            if xi is not None and xi not in current:
                current.append(xi)
        if int(tid) in current:
            self.logger.debug("[秘密] %s 早已告知 %s，无变化", sid, tid)
            return True

        current.append(int(tid))
        cur = self.db.execute(
            "UPDATE secrets SET revealed_to = ? WHERE secret_id = ?",
            (_json_dumps(current), sid))
        if cur is not None:
            self.logger.info("[秘密] id=%s 已告知角色 %s（当前知情 %d 人）",
                             sid, tid, len(current))
        return cur is not None

    def list_revealed_to(
        self,
        cid: Any,
        include_public: bool = True,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """某角色**已经知情**的秘密（他被人告知的那些）。

        ``include_public=True`` 时把 ``status='revealed'``（已公开）的也算进来。
        """
        tid = self._resolve(cid)
        if tid is None:
            return []
        rows = self.db.query(
            "SELECT s.*, c.name AS owner_name FROM secrets s "
            "LEFT JOIN characters c ON c.character_id = s.owner_character_id "
            "WHERE s.status != ? OR ? = 1 "
            "ORDER BY s.secret_id DESC",
            (SECRET_OBSOLETE, 1 if include_public else 0))
        out: List[Dict[str, Any]] = []
        for r in rows:
            if int(r.get("owner_character_id") or 0) == int(tid):
                continue
            revealed = [_to_int(x) for x in _as_list(r.get("revealed_to"))]
            revealed = [x for x in revealed if x is not None]
            if int(tid) in revealed or (
                    include_public and str(r.get("status")) == SECRET_REVEALED):
                out.append(r)
        if limit:
            out = out[:int(limit)]
        return out

    def knows_secret(self, cid: Any, secret_id: Any) -> bool:
        """某角色是否知道这条秘密（持有者本人或被告知者都算）。"""
        secret = self.get_secret(secret_id)
        if secret is None:
            return False
        tid = self._resolve(cid)
        if tid is None:
            return False
        if int(tid) == int(secret["owner_character_id"]):
            return True
        # 已公开（status='revealed'）= 所有人都知道，与 list_revealed_to 保持一致
        if str(secret.get("status")) == SECRET_REVEALED:
            return True
        revealed = [_to_int(x) for x in _as_list(secret.get("revealed_to"))]
        return int(tid) in [x for x in revealed if x is not None]

    def mark_public(self, secret_id: Any) -> bool:
        """把秘密标记为已公开（``status='revealed'``）。"""
        sid = _to_int(secret_id)
        if sid is None:
            return False
        cur = self.db.execute(
            "UPDATE secrets SET status = ? WHERE secret_id = ?",
            (SECRET_REVEALED, sid))
        if cur is not None:
            self.logger.info("[秘密] id=%s 标记为已公开", sid)
        return cur is not None

    def mark_obsolete(self, secret_id: Any) -> bool:
        """把秘密标记为失效（``status='obsolete'``）。"""
        sid = _to_int(secret_id)
        if sid is None:
            return False
        cur = self.db.execute(
            "UPDATE secrets SET status = ? WHERE secret_id = ?",
            (SECRET_OBSOLETE, sid))
        return cur is not None

    def count(self, cid: Any = None, statuses: Optional[Sequence[str]] = None) -> int:
        """秘密条数。"""
        sql = "SELECT COUNT(*) FROM secrets WHERE 1 = 1"
        params: List[Any] = []
        if cid is not None:
            oid = self._resolve(cid)
            if oid is None:
                return 0
            sql += " AND owner_character_id = ?"
            params.append(oid)
        if statuses:
            sl = [s for s in (str(x).strip().lower() for x in statuses)
                  if s in VALID_SECRET_STATUSES]
            if sl:
                marks = ", ".join("?" * len(sl))
                sql += f" AND status IN ({marks})"
                params.extend(sl)
        return int(self.db.scalar(sql, tuple(params), 0) or 0)

    def count_reveals(self, secret_id: Any) -> int:
        """一条秘密已知情人数（不含持有者）。"""
        secret = self.get_secret(secret_id)
        if secret is None:
            return 0
        return len([x for x in _as_list(secret.get("revealed_to"))
                    if _to_int(x) is not None])


# ==============================================================================
# 第 4 批：抽取 / 导入 / 上下文 —— LLMClient / ExtractionResult /
#          PROMPT_SYSTEM / MemoryExtractor / TavoImporter / ContextBuilder
# ==============================================================================

# ---------- 批 4 补充常量 ----------
#: 单次抽取的容量上限（防止一次灌爆数据库）
MAX_EVENTS_PER_EXTRACTION = 20
MAX_MEMORIES_PER_EXTRACTION = 40
MAX_BELIEFS_PER_EXTRACTION = 30
MAX_COMMITMENTS_PER_EXTRACTION = 15
MAX_SECRETS_PER_EXTRACTION = 15
MAX_REL_CHANGES_PER_EXTRACTION = 20
MAX_STATE_CHANGES_PER_EXTRACTION = 30
MAX_KNOWLEDGE_PER_EXTRACTION = 40
MAX_VISIBILITY_PER_EXTRACTION = 60
#: 送入 LLM 的消息条数 / 字符数上限
MAX_LLM_MESSAGES = 20
MAX_LLM_INPUT_CHARS = 4000
# 抽取 prompt 里「本轮涉及的角色」清单上限（防角色多的卡把预算吃光）
ROSTER_MAX_CHARACTERS = 30
# ROSTER_BIO_CHARS = 50   # [#47 10-05] 废 —— roster 不再带 bio
ROSTER_MAX_CHARS = 1500

# [C2] 写入侧判重的候选清单（供 LLM 判断 reinforce / add）
EXTRACT_CANDIDATE_PER_SPEAKER = 5    # 每个说话人最多列几条已有记忆
EXTRACT_CANDIDATE_MAX_SPEAKERS = 6   # 最多列几个说话人（防 prompt 膨胀）
EXTRACT_CANDIDATE_CHARS = 40         # 每条内容截断长度
# [预算保底] 单条消息最多占抽取 prompt 预算的比例（4000 * 0.5 = 2000 字/条）
EXTRACT_SINGLE_MSG_MAX = MAX_LLM_INPUT_CHARS // 2
# 拆条标记行里「角色名 + 分隔符 + 描述」的分隔符（如 👤 己 | 16岁，高中生…）
MARKER_NAME_SEPARATORS = frozenset(("|", "\uff5c", ":", "\uff1a", " ", "\u3000"))
#: 规则抽取的最低门槛
RULE_MIN_TEXT_LEN = 4
RULE_EVENT_MIN_TEXT_LEN = 12
RULE_FACT_MAX_LEN = 300
#: 规则层判定"这是件事"的触发词（正则）
EVENT_PATTERNS: Tuple[str, ...] = (
    r"发生", r"遇到", r"看见", r"看到", r"听说", r"发现", r"来到", r"离开",
    r"战斗", r"受伤", r"救", r"杀死", r"死亡", r"结盟", r"背叛", r"告白",
    r"答应", r"交给", r"得到", r"失去", r"打败", r"去", r"见",
)
#: 抽取来源标记
EXTRACT_SOURCE_LLM = "llm"
EXTRACT_SOURCE_RULE = "rule"

# ---------- TavoImporter ----------
TAVO_MAX_LINE_LEN = 200000
TAVO_DEFAULT_NAME = "unknown"
TAVO_ROLE_USER = "user"
TAVO_ROLE_ASSISTANT = "assistant"
TAVO_ROLE_SYSTEM = "system"

# ---------- ContextBuilder ----------
CONTEXT_MEMORY_LIMIT = 8
CONTEXT_EVENT_LIMIT = 6
CONTEXT_COMMITMENT_LIMIT = 6
CONTEXT_SECRET_LIMIT = 5
CONTEXT_BELIEF_LIMIT = 5
CONTEXT_STANCE_MEMORY_LIMIT = 5
CONTEXT_MAX_CHARS = 6000
#: 【硬约束】以下字样绝对不允许出现在 ContextBuilder 的输出里
FORBIDDEN_CONTEXT_MARKERS: Tuple[str, ...] = (
    "你不知道的事情", "你不知道的事", "未知信息", "你不该知道",
)
#: 兜底约束句（SPEC 原则 7 指定原文）
CONTEXT_SAFETY_LINES: Tuple[str, ...] = (
    "不要忘记以上已经发生的事实。",
    "不要继承其他角色的私人记忆。",
    "不要凭空改变已经建立的关系。",
    "仅依据提供给你的记忆、事实和当前对话作答。",
    "对于没有相关信息的事情，不要自行补全具体事实。",
    "保持你的性格、语气、立场的一致性。",
)


# ==============================================================================
# 18. LLMClient
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【13】LLM 客户端
# ══════════════════════════════════════════════════════════════════════

class LLMClient:
    """OpenAI 兼容 ``/v1/chat/completions`` 的最小客户端（纯标准库）。

    * 只用 ``urllib``，不引入 requests / httpx
    * **所有网络异常一律捕获并返回 None**：连接失败、超时、DNS 失败、
      非 2xx、响应不是 JSON、JSON 里没有 ``choices[0].message.content``
      —— 全部走 None，绝不上抛（抽取环节不能因网络抖动中断）
    * ``chat_json`` 自带重试；``retries`` 表示"首次失败后再试几次"，
      因此最多请求 ``retries + 1`` 次
    """

    def __init__(
        self,
        cfg: Any = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or _get_logger("llm")

        if cfg is None:
            llm_cfg = LLMConfig()
        elif isinstance(cfg, LLMConfig):
            llm_cfg = cfg
        elif hasattr(cfg, "llm"):
            llm_cfg = getattr(cfg, "llm")
        elif isinstance(cfg, dict):
            llm_cfg = LLMConfig(
                **{k: v for k, v in cfg.items()
                   if k in LLMConfig.__dataclass_fields__})
        else:
            raise TypeError(f"LLMClient 无法识别的配置类型：{type(cfg).__name__}")

        self.cfg: LLMConfig = llm_cfg
        self.timeout: float = float(llm_cfg.timeout or LLM_DEFAULT_TIMEOUT)
        self.max_tokens: int = int(llm_cfg.max_tokens or LLM_DEFAULT_MAX_TOKENS)
        self.temperature: float = float(
            llm_cfg.temperature if llm_cfg.temperature is not None
            else LLM_DEFAULT_TEMPERATURE)
        #: 最近一次失败原因（不参与控制流，仅供排障）
        #: 最近一次失败原因（不参与控制流，仅供排障）
        self.last_error: Optional[str] = None
        self.call_count = 0
        self.fail_count = 0
        #: 最近一次 chat_raw 的上游原始响应字节（中继原样回传用，批 6 追加）
        self.last_raw: Optional[bytes] = None
        #: 最近一次 chat_raw 的上游 HTTP 状态码（批 6 追加）
        self.last_status: Optional[int] = None

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        """是否具备调用条件：``enabled=True`` 且 base_url / model 非空、key 不是占位值。"""
        if not bool(self.cfg.enabled):
            return False
        if not str(self.cfg.base_url or "").strip():
            return False
        if not str(self.cfg.model or "").strip():
            return False
        return True

    def endpoint(self) -> str:
        """规范化后的 ``/chat/completions`` 完整地址。"""
        return self.cfg.endpoint()

    def _payload(self, system: str, user: str) -> Dict[str, Any]:
        return {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": str(system or "")},
                {"role": "user", "content": str(user or "")},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

    @staticmethod
    def _extract_content(data: Any) -> Optional[str]:
        """从响应里取正文；content 可能是 str，也可能是分段数组。"""
        if not isinstance(data, dict):
            return None
        try:
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            if not isinstance(first, dict):
                return None
            message = first.get("message") or {}
            if not isinstance(message, dict):
                return None
            content = message.get("content")
        except Exception:
            return None

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for p in content:
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    parts.append(p["text"])
                elif isinstance(p, str):
                    parts.append(p)
            return "".join(parts) if parts else None
        return None

    # ------------------------------------------------------------------
    def chat(self, system: str, user: str) -> Optional[str]:
        """发一次对话补全请求；成功返回正文，任何异常返回 None。"""
        if not self.enabled:
            self.last_error = ("LLM 未启用（enabled / base_url / model 之一不满足）")
            self.logger.debug("[LLM] 跳过调用：%s", self.last_error)
            return None

        self.call_count += 1
        try:
            body = json.dumps(self._payload(system, user),
                              ensure_ascii=False).encode(DEFAULT_ENCODING)
            req = urllib.request.Request(
                self.endpoint(),
                data=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self.cfg.api_key}",
                    "User-Agent": LLM_USER_AGENT,
                    "Accept": "application/json",
                },
                method="POST",
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(LLM_MAX_RESPONSE_BYTES)
            elapsed = time.time() - t0

            data = json.loads(raw.decode(DEFAULT_ENCODING, errors="replace"))
            content = self._extract_content(data)
            if not content:
                self.fail_count += 1
                self.last_error = "响应中没有可用的 choices[0].message.content"
                self.logger.warning("[LLM] %s（耗时 %.2fs）", self.last_error, elapsed)
                return None

            self.last_error = None
            self.logger.info("[LLM] 调用成功 %.2fs，返回 %d 字", elapsed, len(content))
            return content

        except urllib.error.HTTPError as ex:
            self.fail_count += 1
            detail = ""
            try:
                detail = ex.read(500).decode(DEFAULT_ENCODING, errors="replace")
            except Exception:
                pass
            self.last_error = f"HTTP {ex.code} {ex.reason}"
            self.logger.warning("[LLM] 请求失败 %s %s", self.last_error, detail[:200])
        except urllib.error.URLError as ex:
            self.fail_count += 1
            self.last_error = f"URLError: {ex.reason}"
            self.logger.warning("[LLM] 网络错误 %s", self.last_error)
        except (TimeoutError, socket.timeout) as ex:
            self.fail_count += 1
            self.last_error = f"超时: {ex}"
            self.logger.warning("[LLM] 请求超时（timeout=%.0fs）", self.timeout)
        except (json.JSONDecodeError, ValueError) as ex:
            self.fail_count += 1
            self.last_error = f"响应不是合法 JSON: {ex}"
            self.logger.warning("[LLM] %s", self.last_error)
        except Exception as ex:  # 兜底：任何意外异常也不许逃出去
            self.fail_count += 1
            self.last_error = f"{type(ex).__name__}: {ex}"
            self.logger.warning("[LLM] 未预期异常 %s", self.last_error)

        return None

    def chat_raw(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[dict]:
        """把**完整 messages 列表**发给上游，返回原始 JSON 响应 dict（批 6 追加）。

        与 ``chat()`` 的分工：

        * ``chat()``     —— 只接受 system / user 两个字符串，自己拼装载荷
          （抽取环节用）
        * ``chat_raw()`` —— 用于「本地 OpenAI 兼容中继」：把调用方
          （Tavo / SillyTavern）的整段对话原样透传，含多轮 assistant、
          ``name`` 字段、``tool`` 等

        参数
        ----
        * ``temperature`` / ``max_tokens`` 为 ``None`` 时用配置默认值
        * ``extra`` 里的键会覆盖/追加到请求载荷（用于透传 ``model`` /
          ``top_p`` / ``stop`` / ``frequency_penalty`` 等调用方给的字段）

        返回
        ----
        上游响应的原始 JSON ``dict``（含 ``choices`` / ``usage`` 等）；
        未启用、网络异常、非 2xx、响应不是 JSON 对象 —— 一律返回 ``None``。
        最近一次结果记录在 ``self.last_raw``（原始字节）/
        ``self.last_status``（HTTP 状态码）/ ``self.last_error``（错误原因）。
        """
        self.last_raw = None
        self.last_status = None

        if not self.enabled:
            self.last_error = ("LLM 未启用（enabled / base_url / model 之一不满足）")
            self.logger.debug("[LLM] chat_raw 跳过调用：%s", self.last_error)
            return None

        clean: List[Dict[str, Any]] = [
            m for m in (messages or []) if isinstance(m, dict)]
        if not clean:
            self.fail_count += 1
            self.last_error = "messages 为空或格式非法"
            self.logger.warning("[LLM] chat_raw %s", self.last_error)
            return None

        payload: Dict[str, Any] = {
            "model": self.cfg.model,
            "messages": clean,
            "temperature": (self.temperature if temperature is None
                            else float(temperature)),
            "max_tokens": (self.max_tokens if max_tokens is None
                           else int(max_tokens)),
            "stream": False,
        }
        if isinstance(extra, dict):
            for key, value in extra.items():
                if key == "messages":
                    continue
                payload[key] = value

        self.call_count += 1
        try:
            body = json.dumps(payload, ensure_ascii=False).encode(DEFAULT_ENCODING)
            req = urllib.request.Request(
                self.endpoint(),
                data=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self.cfg.api_key}",
                    "User-Agent": LLM_USER_AGENT,
                    "Accept": "application/json",
                },
                method="POST",
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(LLM_MAX_RESPONSE_BYTES)
                status = int(getattr(resp, "status", 200) or 200)
            elapsed = time.time() - t0

            data = json.loads(raw.decode(DEFAULT_ENCODING, errors="replace"))
            if not isinstance(data, dict):
                self.fail_count += 1
                self.last_error = "响应 JSON 不是对象"
                self.logger.warning("[LLM] chat_raw %s（耗时 %.2fs）",
                                    self.last_error, elapsed)
                return None

            self.last_raw = raw
            self.last_status = status
            self.last_error = None
            self.logger.info("[LLM] chat_raw 成功 %.2fs，%d 字节", elapsed, len(raw))
            return data

        except urllib.error.HTTPError as ex:
            self.fail_count += 1
            detail = ""
            try:
                detail = ex.read(500).decode(DEFAULT_ENCODING, errors="replace")
            except Exception:
                pass
            self.last_error = f"HTTP {ex.code} {ex.reason}"
            self.last_status = int(getattr(ex, "code", 0) or 0)
            self.logger.warning("[LLM] chat_raw 请求失败 %s %s",
                                self.last_error, detail[:200])
        except urllib.error.URLError as ex:
            self.fail_count += 1
            self.last_error = f"URLError: {ex.reason}"
            self.logger.warning("[LLM] chat_raw 网络错误 %s", self.last_error)
        except (TimeoutError, socket.timeout) as ex:
            self.fail_count += 1
            self.last_error = f"超时: {ex}"
            self.logger.warning("[LLM] chat_raw 请求超时（timeout=%.0fs）",
                                self.timeout)
        except (json.JSONDecodeError, ValueError) as ex:
            self.fail_count += 1
            self.last_error = f"响应不是合法 JSON: {ex}"
            self.logger.warning("[LLM] chat_raw %s", self.last_error)
        except Exception as ex:  # 兜底：任何意外异常也不许逃出去
            self.fail_count += 1
            self.last_error = f"{type(ex).__name__}: {ex}"
            self.logger.warning("[LLM] chat_raw 未预期异常 %s", self.last_error)

        return None

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Iterator[bytes]:
        """以 ``stream=true`` 请求上游，**逐块产出上游原始 SSE 字节**（批 8 追加）。

        这是 ``chat_raw()`` 的流式版本，专给「本地 OpenAI 兼容中继」转发 SSE：
        调用方（Tavo / SillyTavern）坚持发 ``stream: true`` 时，本方法把上游
        ``text/event-stream`` 的每一行（``data: {...}\\n\\n``）原样吐出来，
        中继层直接写回客户端即可，不需要解析、不需要重组。

        推荐用法（**先 peek 一块**再决定响应头，这样上游连不上时还能回普通
        JSON 502，而不是已经发了 200 才失败）::

            gen = llm.chat_stream(msgs, max_tokens=800)
            first = next(gen, None)
            if first is None:        # 失败原因在 llm.last_error
                ...                  # 回 JSON 错误（此时一个字节都没发）
            else:
                send(200, "text/event-stream")
                write(first)
                for chunk in gen:
                    write(chunk); flush()

        失败约定与 ``chat_raw()`` 一致：未启用 / messages 非法 / 网络异常 /
        非 2xx —— **一个块都不产出**，原因写进 ``self.last_error``
        （非 2xx 时 ``self.last_status`` 是上游状态码）；**绝不抛异常**给调用方。
        流读到一半断开只记日志，已产出的块照旧交付。
        """
        self.last_raw = None
        self.last_status = None

        if not self.enabled:
            self.last_error = ("LLM 未启用（enabled / base_url / model 之一不满足）")
            self.logger.debug("[LLM] chat_stream 跳过调用：%s", self.last_error)
            return

        clean: List[Dict[str, Any]] = [
            m for m in (messages or []) if isinstance(m, dict)]
        if not clean:
            self.fail_count += 1
            self.last_error = "messages 为空或格式非法"
            self.logger.warning("[LLM] chat_stream %s", self.last_error)
            return

        payload: Dict[str, Any] = {
            "model": self.cfg.model,
            "messages": clean,
            "temperature": (self.temperature if temperature is None
                            else float(temperature)),
            "max_tokens": (self.max_tokens if max_tokens is None
                           else int(max_tokens)),
            "stream": True,
        }
        if isinstance(extra, dict):
            for key, value in extra.items():
                # messages 上面已拼好；stream 必须是 True（本方法专用）
                if key in ("messages", "stream"):
                    continue
                payload[key] = value

        self.call_count += 1
        t0 = time.time()
        resp: Any = None
        try:
            body = json.dumps(payload, ensure_ascii=False).encode(DEFAULT_ENCODING)
            req = urllib.request.Request(
                self.endpoint(),
                data=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self.cfg.api_key}",
                    "User-Agent": LLM_USER_AGENT,
                    "Accept": "text/event-stream",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as ex:
            self.fail_count += 1
            detail = ""
            try:
                detail = ex.read(500).decode(DEFAULT_ENCODING, errors="replace")
            except Exception:
                pass
            self.last_error = f"HTTP {ex.code} {ex.reason}"
            self.last_status = int(getattr(ex, "code", 0) or 0)
            self.logger.warning("[LLM] chat_stream 请求失败 %s %s",
                                self.last_error, detail[:200])
            return
        except urllib.error.URLError as ex:
            self.fail_count += 1
            self.last_error = f"URLError: {ex.reason}"
            self.logger.warning("[LLM] chat_stream 网络错误 %s", self.last_error)
            return
        except (TimeoutError, socket.timeout) as ex:
            self.fail_count += 1
            self.last_error = f"超时: {ex}"
            self.logger.warning("[LLM] chat_stream 请求超时（timeout=%.0fs）",
                                self.timeout)
            return
        except Exception as ex:  # 兜底：连不上也绝不抛给调用方
            self.fail_count += 1
            self.last_error = f"{type(ex).__name__}: {ex}"
            self.logger.warning("[LLM] chat_stream 未预期异常 %s", self.last_error)
            return

        self.last_status = int(getattr(resp, "status", 200) or 200)
        self.last_error = None
        self.logger.info("[LLM] chat_stream 已连上上游 %s（%.2fs，超时 %.0fs）",
                         self.last_status, time.time() - t0, self.timeout)

        chunks = 0
        total = 0
        try:
            for line in resp:   # 逐行迭代：SSE 一帧两行，原样转发
                if not line:
                    continue
                chunks += 1
                total += len(line)
                if total > LLM_MAX_STREAM_BYTES:
                    self.last_error = ("上游流超过 %d 字节，已主动截断"
                                       % LLM_MAX_STREAM_BYTES)
                    self.logger.warning("[LLM] chat_stream %s", self.last_error)
                    break
                yield bytes(line)
        except (TimeoutError, socket.timeout) as ex:
            self.last_error = f"流式读取超时: {ex}"
            self.logger.warning("[LLM] chat_stream %s（已收 %d 段）",
                                self.last_error, chunks)
        except GeneratorExit:     # 调用方提前 close()，照旧关掉上游连接
            raise
        except Exception as ex:
            self.last_error = f"{type(ex).__name__}: {ex}"
            self.logger.warning("[LLM] chat_stream 流中断 %s（已收 %d 段）",
                                self.last_error, chunks)
        finally:
            try:
                resp.close()
            except Exception:
                pass
            self.logger.info("[LLM] chat_stream 结束：%d 段 / %d 字节",
                             chunks, total)

    def chat_json(
        self,
        system: str,
        user: str,
        retries: int = LLM_DEFAULT_RETRIES,
    ) -> Optional[dict]:
        """请求并解析 JSON 对象；全部失败返回 None。

        ``retries`` = 首次失败后再试的次数，故最多请求 ``retries + 1`` 次。
        数组型返回会包成 ``{"items": [...]}`` 以免丢数据。
        """
        try:
            times = max(0, int(retries)) + 1
        except Exception:
            times = 1

        for attempt in range(1, times + 1):
            text = self.chat(system, user)
            if not text:
                self.logger.warning("[LLM] 第 %d/%d 次尝试未取到文本",
                                    attempt, times)
            else:
                parsed = _parse_json_safe(text, None)
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    try:
                        if all(isinstance(x, dict) for x in parsed):
                            self.logger.info(
                                "[LLM] 返回为 JSON 数组（%d 项），已包成 items",
                                len(parsed))
                            return {"items": parsed}
                    except Exception:
                        pass
                self.logger.warning(
                    "[LLM] 第 %d/%d 次返回不是合法 JSON 对象（前 120 字：%r）",
                    attempt, times, str(text)[:120])

            if attempt < times:
                time.sleep(LLM_RETRY_BACKOFF_SEC * attempt)

        self.logger.warning("[LLM] %d 次尝试全部失败，最后错误：%s",
                            times, self.last_error)
        return None

    def describe(self) -> Dict[str, Any]:
        """可观测性摘要（不含密钥）。"""
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint(),
            "model": self.cfg.model,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "call_count": self.call_count,
            "fail_count": self.fail_count,
            "last_error": self.last_error,
        }

    def __repr__(self) -> str:
        return (f"<LLMClient enabled={self.enabled} model={self.cfg.model!r} "
                f"calls={self.call_count} fails={self.fail_count}>")


# ==============================================================================
# 19. ExtractionResult
# ==============================================================================

@dataclass

# ══════════════════════════════════════════════════════════════════════
# 【14】抽取器
# ══════════════════════════════════════════════════════════════════════

class ExtractionResult:
    """一次抽取的产出容器。

    9 个载荷字段
    ------------
    * ``events``               —— 事件（含 ``participants``）
    * ``memories``             —— 记忆
    * ``beliefs``              —— 信念
    * ``commitments``          —— 承诺
    * ``secrets``              —— 秘密
    * ``relationship_changes`` —— 关系变化
    * ``state_changes``        —— 状态变化
    * ``knowledge_updates``    —— 非事件型知识
    * ``visibility_updates``   —— 可见性更新（含 state / partial_content /
      source / source_message_id）

    ``visibility_updates`` 是 ``events[].participants`` 的**扁平化配套视图**：
    LLM 既可以写在事件里，也可以单独列出；两条路都会被收敛成同一份列表，
    由 Python 层统一校验后写库。
    """

    events: List[Dict[str, Any]] = field(default_factory=list)
    memories: List[Dict[str, Any]] = field(default_factory=list)
    beliefs: List[Dict[str, Any]] = field(default_factory=list)
    commitments: List[Dict[str, Any]] = field(default_factory=list)
    secrets: List[Dict[str, Any]] = field(default_factory=list)
    relationship_changes: List[Dict[str, Any]] = field(default_factory=list)
    state_changes: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_updates: List[Dict[str, Any]] = field(default_factory=list)
    visibility_updates: List[Dict[str, Any]] = field(default_factory=list)

    # ---- 元信息（非载荷）----
    mode: str = ""
    source: str = ""
    message_count: int = 0
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    PAYLOAD_FIELDS: Tuple[str, ...] = (
        "events", "memories", "beliefs", "commitments", "secrets",
        "relationship_changes", "state_changes", "knowledge_updates",
        "visibility_updates",
    )

    # ------------------------------------------------------------------
    def counts(self) -> Dict[str, int]:
        """各载荷字段的条数。"""
        return {f: len(getattr(self, f) or []) for f in self.PAYLOAD_FIELDS}

    def total(self) -> int:
        """载荷总条数。"""
        return sum(self.counts().values())

    def is_empty(self) -> bool:
        """是否完全没抽到东西。"""
        return self.total() == 0

    def cap(self) -> "ExtractionResult":
        """按 ``MAX_*_PER_EXTRACTION`` 截断各字段，防止一次灌爆数据库。"""
        limits = {
            "events": MAX_EVENTS_PER_EXTRACTION,
            "memories": MAX_MEMORIES_PER_EXTRACTION,
            "beliefs": MAX_BELIEFS_PER_EXTRACTION,
            "commitments": MAX_COMMITMENTS_PER_EXTRACTION,
            "secrets": MAX_SECRETS_PER_EXTRACTION,
            "relationship_changes": MAX_REL_CHANGES_PER_EXTRACTION,
            "state_changes": MAX_STATE_CHANGES_PER_EXTRACTION,
            "knowledge_updates": MAX_KNOWLEDGE_PER_EXTRACTION,
            "visibility_updates": MAX_VISIBILITY_PER_EXTRACTION,
        }
        for f, limit in limits.items():
            val = list(getattr(self, f) or [])
            if len(val) > limit:
                setattr(self, f, val[:limit])
        return self

    def describe(self) -> str:
        """一行人类可读摘要。"""
        body = " ".join("%s=%d" % (k, v)
                        for k, v in self.counts().items() if v)
        head = "mode=%s source=%s" % (self.mode or "-", self.source or "-")
        return head + " total=%d" % self.total() + (" | " + body if body else "")

    def to_dict(self) -> Dict[str, Any]:
        """导出为纯 dict（含元信息）。"""
        out: Dict[str, Any] = {f: list(getattr(self, f) or [])
                               for f in self.PAYLOAD_FIELDS}
        out.update({
            "mode": self.mode,
            "source": self.source,
            "message_count": self.message_count,
            "error": self.error,
            "warnings": list(self.warnings),
        })
        return out


# ==============================================================================
# 20. PROMPT_SYSTEM
# ==============================================================================
#
# 本常量严格实现 SPEC.md「LLM 系统提示词必须包含」的 11 条。
# ==============================================================================

PROMPT_SYSTEM = """你是「多角色长期记忆引擎」的信息抽取器。你的唯一任务是把给定的对话文本转成结构化 JSON。

【最重要的一条真理】
事件发生了 ≠ 所有人知道了 ≠ 所有人记住了 ≠ 所有人相信了 ≠ 所有人对它采取相同态度。
你抽取的一切都必须守住这条边界。

【必须遵守的 11 条】
1. 只提取值得长期记忆的内容，忽略寒暄闲聊（你好、谢谢、嗯、哈哈之类一律不要输出）。
2. 记忆必须带视角：owner_name 是谁的视角，content 就用谁的第一人称写（"我看到…"、"他说…"）。同一事件在不同角色那里是不同的记忆，措辞必须体现各自的立场与信息量。
3. 不要机械地为所有在场角色创建记忆。只为**实际参与、亲眼观察或确实受到影响**、且这件事值得长期记住的角色生成独立视角 memory。旁观无关者不要给。
4. 不在现场的角色**绝不能**获得该事件的 KNOWN 记录。不要因为"他们关系好"或"他迟早会知道"就替别人写认知。
5. state 填 SUSPECTED 或 RUMORED 时，partial_content 必须写出该角色**实际知道的那一部分**（他到底听到了什么、看到了什么片段），不能给全貌，也不能写"他不知道什么"。
6. 不要编造没有发生过的事。原文没提到的人名、时间、数字、动机、因果，一律不要写。
7. beliefs.kind 填 FACT 不要由你生成（FACT 由规则层负责）。你只能输出 BELIEF / ATTITUDE / SELF_BELIEF / JUDGMENT 四种。
8. Visibility 不自动传播。一个角色知道，不代表别人知道。只有发生了实际的**信息披露、共同观察或新的有效事件**，才能让另一个角色获得 visibility。
9. 事件型 memory 必须引用对应的 event（用 source_event_index 指向本次输出 events 数组的下标，从 0 开始）。
10. 不要通过 knowledge.event_id 把事件型知识绕过 event_visibility 写进 knowledge。非事件型 knowledge 的 event_id 必须为 null。
11. 每个 participant 尽量带上 source_message_id（下方消息列表里的编号），以便 Python 层判断这次是不是"新来源"。

【关于 user（用户）的动作归属】

user 的第一人称动作、感受、命令，属于 user 本人，不属于任何角色。
不要为任何角色生成"我在做 user 的动作"这类 memory。

判断规则：
· user 做了 X → 不为任何角色生成 memory
· 有角色亲眼看到/听到 user 做 X → 给那个角色生成"我看到 user 做 X"（角色视角，不是 user 视角）
· 有角色被 user 做了什么 → 给那个角色生成"user 对我做了 X"（角色被作用的视角）
· user 说的话（对话）→ 只有实际在场、听到的角色才能记

反例（绝对禁止）：
  user 消息："我推了丙一把"
  ❌ owner=甲，"我推了丙一把"   ← 甲不会做这个动作
  ✅ owner=丙，"老爷推了我一把"   ← 对，丙是被作用的角色

正例：
  user 消息："我打了丁一拳"
  ✅ owner=丁，"老爷打了我一拳"
  ❌ 不生成任何角色的"我打了丁一拳"

核心：memory 的视角是"角色的视角"，不是 user 的视角。
user 的第一人称动作，绝不能原样落到某个角色名下。

【输出结构】
{
  "events": [{
    "summary": "客观摘要，第三人称，不带任何角色立场",
    "event_type": "world_event|conflict|commitment|secret|dialogue|revelation|travel|gift|injury|meeting|other",
    "importance": 0.0,
    "emotional_intensity": 0.0,
    "occurred_at": "ISO-8601 或 null",
    "location": "" ,
    "is_factual": 1,
    "participants": [{
      "name": "角色名",
      "role_in_event": "speaker|actor|victim|witness|nearby|mentioned_only",
      "present": 1,
      "state": "KNOWN|SUSPECTED|RUMORED",
      "partial_content": "state 为 SUSPECTED/RUMORED 时必填；KNOWN 时留空",
      "source": "firsthand|heard_from:某人|inferred|witnessed_partially",
      "source_message_id": "消息编号",
      "confidence": 0.7
    }]
  }],
  "memories": [{
    "owner_name": "谁的视角",
    "memory_type": "episodic|semantic|relationship|emotional|procedural|secret|commitment|conflict|preference|identity|world_event",
    "content": "该角色第一人称的这条记忆，≤80字，只写核心事实或感受",
    "importance": 0.0,
    "confidence": 0.0,
    "emotional_intensity": 0.0,
    "source_type": "USER|OBSERVATION|INFERENCE|HEARSAY|UNKNOWN — 用户亲口陈述=USER，剧情中亲眼所见=OBSERVATION，听他人转述=HEARSAY，跨轮推断=INFERENCE，不确定=UNKNOWN",
    "source_event_index": 0,
    "action": "add | reinforce",
    "reinforce_id": "上面【已有记忆】里某条的 #id；action=add 时填 null"
  }],
  "beliefs": [{
    "owner_name": "谁",
    "kind": "BELIEF|ATTITUDE|SELF_BELIEF|JUDGMENT",
    "subject_kind": "person|event|fact|self",
    "subject_ref": "对象（人物名 / 事件短语 / 事实短语 / self）",
    "statement": "第一人称陈述",
    "confidence": 0.7,
    "based_on_event_index": 0
  }],
  "commitments": [{
    "promiser_name": "承诺者",
    "promisee_name": "受诺者，没有明确对象填 null",
    "content": "承诺的具体内容",
    "deadline": "ISO-8601 或 null"
  }],
  "secrets": [{
    "owner_name": "保守秘密的人",
    "content": "秘密内容",
    "subject": "隐瞒的对象或主题"
  }],
  "relationship_changes": [{
    "from_name": "谁对谁",
    "to_name": "谁",
    "field": "trust|affection|resentment|familiarity|respect|fear|dependency",
    "delta": -0.3,
    "reason": "变化原因",
    "based_on_event_index": 0
  }],
  "state_changes": [{
    "character_name": "谁",
    "field": "emotion|mood|anger|fear|stress|relationship_state|current_goal|current_location|physical_state|mental_context|unresolved_conflicts|summary",
    "value": "新值（数值字段填 0~1 的数）",
    "reason": "原因"
  }],
  "knowledge_updates": [{
    "owner_name": "谁知道",
    "subject": "非事件型事实，如「明喜欢吃苹果」",
    "status": "KNOWN|UNKNOWN|SUSPECTED|RUMORED|FORGOTTEN",
    "confidence": 0.7,
    "source": "消息编号或来源说明",
    "event_id": null
  }],
  "visibility_updates": [{
    "event_index": 0,
    "character": "角色名",
    "state": "KNOWN|SUSPECTED|RUMORED",
    "partial_content": "",
    "source": "firsthand|heard_from:某人|inferred|witnessed_partially",
    "source_message_id": "消息编号",
    "confidence": 0.7,
    "present": 1,
    "role_in_event": "speaker|actor|victim|witness|nearby|mentioned_only"
  }]
}

【关于 action（重要）】
对每条 memory，判断它和上面【已有记忆】里某条是不是"同一概念 / 同一事件 / 同一规矩"
（用词可以不同，意思一样就算）。
  · 是 → action="reinforce"，reinforce_id 填那条的 #id（整数）
  · 否 / 判不准 → action="add"，reinforce_id 填 null
例：
  "守住边界" 和 "越界不行" → 同概念 → reinforce
  "答应他明天去" 和 "说好了明天去" → 同事件 → reinforce
  "她说今天很开心" 和 "今天天气好" → 不同 → add
reinforce_id 只能填【已有记忆】里出现过的 id，不许编。
★ 只有上面确实给出了【已有记忆】段时才可能 reinforce；没有那段就一律 add。

【本轮输出不要自重复】

同一轮输出里，不要针对同一件事写多条 memories。
两件"用词不同、意思相同"的事，只输出一条。

判断标准 —— 以下情况属于"同一件事"，合并成一条：
  · 同一行为的不同描述（"她咬住嘴唇" / "她把呻吟咬回去"）
  · 同一情绪的多角度（"我又羞又怕" / "我怕被人听见"）
  · 同一时刻的连续动作（"他进来" / "他开口说话"）
  · 同一承诺的两种措辞（"答应他去" / "说好了去"）
  · 同一感受的两层表达（"我心里疼" / "我替他难受"）

只有"不同时间""不同对象""不同因果"的事，才拆成多条。
宁可少写一条，也不要为了凑数把同一件事拆两半。

【取值约束】
- 所有 importance / emotional_intensity / confidence 都是 0~1 的小数
- state 只有三种：KNOWN（明确知道）、SUSPECTED（怀疑）、RUMORED（听说）。
  完全不知道的角色**不要出现在任何列表里** —— 没有记录就等于不知道。
- relationship_changes 的 delta 绝对值不得超过 0.5，一次最多调整 2 个维度。
  只要本轮对话中角色对某人的感受出现可见变化（好感/反感/信任/畏惧等的增减），就输出这一项；
  完全无情感波动的日常寒暄可以不输出。
- 不确定的字段填 null，没有内容的数组填 []。
- memories.content 必须 ≤ 80 字。只写核心事实或感受，
  不写场景描写、比喻、心理独白。
  正例："老爷说某公子是女扮男装，我心里松了口气"
  反例："我在书房听老爷说破，那位某公子是女扮男装的小姐。
    难怪那身儒衫撑得空、腰身也细..."
- 一段剧情涉及多件事时，拆成多条记忆，每条只写一件。
- 只对 memories.content 生效。

【怎么读下面的输入】
用户消息会以「[编号] 说话人: 正文」的形式给出。引用某条消息时，
source_message_id 填那个编号。events 的下标从 0 开始，供 source_event_index 引用。

只输出 JSON。不要输出解释、markdown 代码围栏、任何前后缀文字。第一个字符必须是 {。"""


# ==============================================================================
# 21. MemoryExtractor —— 规则 + LLM 提取
# ==============================================================================

class MemoryExtractor:
    """把对话消息转成 ``ExtractionResult``（**只产出提案，不写数据库**）。

    两种模式（SPEC「LLM 提取器」段）：

    * ``mode='fast'``            —— 不调用 LLM，纯规则
    * ``mode='normal'/'deep'``   —— LLM 启用就调 LLM；**失败重试 2 次后回退规则**

    规则层能产出（``generated_by='rule'``）：

    * 明确承诺（正则：我答应/保证/发誓/承诺）
    * 明确秘密（正则：不要告诉/这是秘密）
    * 情绪词识别（爱/恨/怕/怒/喜）
    * 重要性粗估（关键词 + 长度 + 情绪）
    * 说话人本人 -> 一条 **FACT** belief（**只针对事件型事实**）
    * 说话人本人 -> 该事件的 **KNOWN** visibility（若对应 event）

    规则层**不产出**：``BELIEF`` / ``ATTITUDE`` / ``JUDGMENT`` / 关系变化。

    LLM 层产出的提案在这里做第一道 Python 层消毒：

    * LLM 给 ``kind='FACT'`` -> 降级为 ``BELIEF`` 并告警（FACT 只能来自规则层）
    * ``relationship_changes`` 的 ``|delta| > 0.5`` -> 直接丢弃该条
    * ``knowledge_updates.event_id`` -> 强制置 None（事件型知识必须走 visibility）
    * ``state='SUSPECTED'/'RUMORED'`` 但 ``partial_content`` 为空 -> 丢弃该 participant
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        llm: Optional[LLMClient] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.llm = llm
        self.config = config
        self.logger = logger or _get_logger("extractor")

    # ==================================================================
    # 输入归一化
    # ==================================================================
    def _normalize_messages(
        self,
        messages: Sequence[Any],
    ) -> List[Dict[str, Any]]:
        """把各种形态的输入消息统一成内部结构。

        接受 dict（``name`` / ``mes`` 或 ``content`` / ``is_user`` /
        ``is_system`` / ``send_date``）、或 ``(name, text)`` 二元组、或纯字符串。
        """
        out: List[Dict[str, Any]] = []
        for i, raw in enumerate(messages or []):
            name = TAVO_DEFAULT_NAME
            text = ""
            is_user = False
            is_system = False
            send_date: Optional[str] = None
            mid: Optional[str] = None

            if isinstance(raw, dict):
                name = str(raw.get("name") or raw.get("speaker")
                           or raw.get("owner_name") or TAVO_DEFAULT_NAME)
                text = str(raw.get("mes") if raw.get("mes") is not None
                           else (raw.get("content") or raw.get("text") or ""))
                is_user = bool(raw.get("is_user"))
                is_system = bool(raw.get("is_system"))
                send_date = _norm_iso(raw.get("send_date"), None)
                mid = _bounded_str(raw.get("message_id"), 128) or None
            elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
                name = str(raw[0] or TAVO_DEFAULT_NAME)
                text = str(raw[1] or "")
            else:
                text = str(raw or "")

            text = text.strip()
            if not text:
                continue
            if not mid:
                mid = _sha("%s|%s|%s" % (name, send_date or "", text))
            out.append({
                "index": i,
                "name": name.strip() or TAVO_DEFAULT_NAME,
                "text": text,
                "is_user": is_user,
                "is_system": is_system,
                "send_date": send_date,
                "message_id": mid,
            })
            if len(out) >= MAX_LLM_MESSAGES:
                break
        return out

    @staticmethod
    def _build_user_prompt(msgs: Sequence[Dict[str, Any]],
                           roster: str = "",
                           memory_candidates: str = "") -> str:
        """拼成「[编号] 说话人: 正文」的可引用输入。

        ``roster``：本卡「本轮涉及的角色」清单（规范名 + 身份 / 性格），
        由调用方算好传入，可为空。

        memory_candidates：本批说话人的近期记忆清单（供 LLM 判重），
        同样由调用方算好传入 —— 本方法自身仍不查库。
        """
        parts: List[str] = []
        total = 0
        for msg in msgs:
            _txt = str(msg["text"] or "")
            # [空窗口修复] 客户端有时把整段「写作要求 / 提示块」当一条 user 消息发来。
            # 它动辄 4000+ 字，会把 MAX_LLM_INPUT_CHARS 一次占满，而原来的
            # `if total + len(line) > MAX: break` 会让 parts 直接为空 ——
            # 送给 LLM 的 prompt 里一条对话都没有，模型于是凭空编出整套事件/角色
            # （实测：窗口里是「某卡」，返回里是角色G/角色H/角色I）。
            if _is_card_rule_text(_txt):
                # 卡规则文本不是对话 → 整条不喂给抽取 LLM
                logging.getLogger(APP_NAME).info(
                    "[提取] 跳过卡规则文本：len=%d 头=%r",
                    len(_txt), _txt[:24])
                continue
            if _is_scaffold_text(_txt):
                if not msg.get("is_user"):
                    continue          # 非 user 消息：保持原有「整条跳过」
                _ex = extract_real_user_text(_txt)
                if _ex["status"] == "success":
                    logging.getLogger(APP_NAME).info(
                        "[提取] 用户正文已从提示块里捞回：raw_len=%d -> %d 字",
                        len(_txt), len(_ex["text"]))
                    _txt = _ex["text"]
                else:
                    logging.getLogger(APP_NAME).warning(
                        "[提取] 用户正文提取失败 raw_len=%d status=%s 退回=跳过",
                        len(_txt), _ex["status"])
                    continue
            tag = "（旁白）" if msg["is_system"] else ""
            line = "[%s] %s%s: %s" % (msg["message_id"], msg["name"], tag, _txt)
            room = MAX_LLM_INPUT_CHARS - total
            if room <= 0:
                break
            # [预算保底] 单条最多占一半预算，剩下的留给后面的消息。
            # 否则一条超长消息（卡规则 / 提示块）会把预算吃光，
            # 真正的对话一条都进不来（实测 6739 字规则文本挤掉了全部对话）。
            room = min(room, EXTRACT_SINGLE_MSG_MAX)
            if len(line) > room:
                line = line[:room] + "…（截断）"   # 单条超长 → 截断，不整锅端掉
            parts.append(line)
            total += len(line)
        head = ("以下是待抽取的对话。请在 events/memories 等各项里，"
                "用方括号里的编号作为 source_message_id。\n\n")
        if not parts:
            return ""      # 调用方据此跳过 LLM，退回规则抽取
        return head + (roster or "") + (memory_candidates or "") + "\n".join(parts)

    def _build_memory_candidates(self, msgs: Sequence[Dict[str, Any]]) -> str:
        """拼一段【已有记忆（供判重）】—— 每个说话人最近/最强的 N 条。

        说话人 = msgs 里非 user、非 system 且 name 非空的角色（去重保序）。
        状态取 active / reinforced —— reinforce 会把 active 改成 reinforced，
        若只查 active，被强化过的那条下一轮就从候选里消失，判重会自我失效。
        查不到 / 出错 → 返回 ""（绝不抛异常，抽取照常进行）。
        """
        try:
            names: List[str] = []
            for m in msgs or []:
                if m.get("is_user") or m.get("is_system"):
                    continue
                _nm = str(m.get("name") or "").strip()
                if _nm and _nm not in names:
                    names.append(_nm)
            if not names:
                return ""
            blocks: List[str] = []
            for _nm in names[:EXTRACT_CANDIDATE_MAX_SPEAKERS]:
                _cid = self.char_mgr.resolve_id(_nm) if self.char_mgr else None
                if _cid is None:
                    continue
                rows = self.db.query(
                    "SELECT memory_id, content FROM memories "
                    "WHERE owner_character_id = ? "
                    "AND status IN ('active', 'reinforced') "
                    "ORDER BY recall_strength DESC, created_at DESC LIMIT ?",
                    (int(_cid), EXTRACT_CANDIDATE_PER_SPEAKER))
                if not rows:
                    continue
                lines: List[str] = []
                for r in rows:
                    _c = " ".join(str(r["content"] or "").split())
                    if len(_c) > EXTRACT_CANDIDATE_CHARS:
                        _c = _c[:EXTRACT_CANDIDATE_CHARS] + "…"
                    lines.append("  #%s %s" % (r["memory_id"], _c))
                blocks.append("%s：\n%s" % (_nm, "\n".join(lines)))
            if not blocks:
                return ""
            return ("【已有记忆（供判重）】\n"
                    "（若新记忆与下列某条是同一概念/事件/规矩（用词不同也算），"
                    "则输出 action=reinforce + reinforce_id=#id；否则 action=add）\n"
                    + "\n".join(blocks) + "\n\n")
        except Exception as ex:
            self.logger.warning("[抽取] 生成判重候选失败（已忽略）：%s", ex)
            return ""

    # ==================================================================
    # 统一入口
    # ==================================================================
    def extract_from_messages(
        self,
        messages: Sequence[Any],
        mode: str = DEFAULT_MODE,
        roster: str = "",
    ) -> ExtractionResult:
        """抽取消息，返回 ``ExtractionResult``。

        ``mode='fast'`` 强制纯规则；``normal`` / ``deep`` 在 LLM 可用时走 LLM，
        **LLM 失败（含重试 2 次都失败）自动回退规则**，绝不返回 None。
        """
        md = str(mode or DEFAULT_MODE).strip().lower()
        if md not in VALID_MODES:
            self.logger.warning("[抽取] 未知 mode=%r，回落为 %s", mode, DEFAULT_MODE)
            md = DEFAULT_MODE

        msgs = self._normalize_messages(messages)
        if not msgs:
            res = ExtractionResult(mode=md, source=EXTRACT_SOURCE_RULE,
                                   message_count=0)
            res.warnings.append("没有可抽取的消息")
            return res

        wants_llm = md in LLM_MODES
        if wants_llm and self.llm is not None and getattr(self.llm, "enabled", False):
            parsed = self._llm_extract(msgs, md, roster)
            if parsed is not None:
                parsed.cap()
                self.logger.info("[抽取] LLM 抽取成功：%s", parsed.describe())
                return parsed
            self.logger.warning(
                "[抽取] LLM 抽取失败（已重试 %d 次），回退规则模式",
                LLM_DEFAULT_RETRIES)
        elif wants_llm:
            self.logger.info("[抽取] LLM 未启用，使用规则模式")

        res = self._rule_extract(msgs)
        res.mode = md
        res.cap()
        self.logger.info("[抽取] 规则抽取完成：%s", res.describe())
        return res

    # ==================================================================
    # 规则抽取
    # ==================================================================
    def _match_any(self, text: str, patterns: Sequence[str]) -> Optional[str]:
        """返回第一个命中的正则（原样返回匹配到的片段），都不中返回 None。"""
        t = str(text or "")
        for pat in patterns or ():
            try:
                mm = re.search(pat, t)
            except re.error:
                continue
            if mm:
                return mm.group(0)
        return None

    def _detect_emotion(self, text: str) -> Tuple[str, float]:
        """情绪词识别，返回 ``(情绪标签, 强度 0~1)``。

        命中多个词时取命中最多的一类；没有命中返回 ``("", 0.0)``。
        """
        t = str(text or "")
        if not t:
            return "", 0.0
        best_label = ""
        best_hits = 0
        for label, words in EMOTION_WORDS:
            hits = sum(1 for w in words if w in t)
            if hits > best_hits:
                best_label, best_hits = label, hits
        if not best_hits:
            return "", 0.0
        intensity = min(1.0, 0.3 + EMOTION_INTENSITY_STEP * (best_hits - 1))
        return best_label, intensity

    def _estimate_importance(self, text: str,
                             emotion_intensity: float = 0.0) -> float:
        """重要性粗估：关键词 + 长度 + 情绪，返回值夹在 0.0~1.0。"""
        t = str(text or "")
        score = 0.35
        for kw, bonus in IMPORTANCE_KEYWORDS:
            if kw in t:
                score += bonus
        length = len(t)
        if length >= 80:
            score += 0.15
        elif length >= 40:
            score += 0.08
        elif length < 12:
            score -= 0.10
        score += 0.20 * _clamp(emotion_intensity, 0.0, 1.0, 0.0)
        return _clamp(score, 0.05, 1.0, 0.35)

    def _rule_extract(self, messages: Sequence[Any]) -> ExtractionResult:
        """纯规则抽取（不调用 LLM，不生成 BELIEF/ATTITUDE/JUDGMENT/关系变化）。"""
        msgs = self._normalize_messages(messages)
        res = ExtractionResult(mode=MODE_FAST, source=EXTRACT_SOURCE_RULE,
                               message_count=len(msgs))

        for msg in msgs:
            text = msg["text"]
            speaker = msg["name"]

            if msg["is_system"]:
                continue
            if _is_trivial(text) or len(text) < RULE_MIN_TEXT_LEN:
                continue

            emotion_label, emotion_intensity = self._detect_emotion(text)
            importance = self._estimate_importance(text, emotion_intensity)
            occurred = msg["send_date"] or now_iso()
            mid = msg["message_id"]

            hit_commit = self._match_any(text, COMMITMENT_PATTERNS)
            hit_secret = self._match_any(text, SECRET_PATTERNS)
            hit_event = self._match_any(text, EVENT_PATTERNS)
            is_event = (
                len(text) >= RULE_EVENT_MIN_TEXT_LEN
                and bool(hit_event or hit_commit or hit_secret)
            )

            event_index: Optional[int] = None
            summary = ""

            # ---- 事件（规则层判定的事件型事实）----
            if is_event:
                summary = text[:RULE_SUMMARY_MAX_LEN]
                if len(text) > RULE_SUMMARY_MAX_LEN:
                    summary += "…"
                event_index = len(res.events)
                res.events.append({
                    "summary": summary,
                    "event_type": (EVENT_TYPE_COMMITMENT if hit_commit
                                   else EVENT_TYPE_SECRET if hit_secret
                                   else EVENT_TYPE_WORLD),
                    "importance": importance,
                    "emotional_intensity": emotion_intensity,
                    "occurred_at": occurred,
                    "location": "",
                    "is_factual": 1,
                    "source_message_ids": [mid],
                    "participants": [{
                        "name": speaker,
                        "role_in_event": "speaker",
                        "present": 1,
                        "state": VIS_KNOWN,
                        "partial_content": "",
                        "source": SOURCE_FIRSTHAND,
                        "source_message_id": mid,
                        "confidence": 0.9,
                    }],
                    "_source": EXTRACT_SOURCE_RULE,
                })

                # 说话人本人的记忆（内容就是他自己的原话 —— 天然第一人称）
                res.memories.append({
                    "owner_name": speaker,
                    "memory_type": MEM_TYPE_EPISODIC,
                    "content": text[:MEM_CONTENT_MAX_LEN],
                    "importance": importance,
                    "confidence": 0.9,
                    "emotional_intensity": emotion_intensity,
                    "is_subjective": 1,
                    "source_event_index": event_index,
                    "source_message_id": mid,
                    "tags": ["rule"],
                    "_source": EXTRACT_SOURCE_RULE,
                })

                # 说话人本人对该事件的 KNOWN visibility
                res.visibility_updates.append({
                    "event_index": event_index,
                    "character": speaker,
                    "state": VIS_KNOWN,
                    "partial_content": "",
                    "source": SOURCE_FIRSTHAND,
                    "source_message_id": mid,
                    "confidence": 0.9,
                    "present": 1,
                    "role_in_event": "speaker",
                    "_source": EXTRACT_SOURCE_RULE,
                })

                # 说话人本人的 FACT belief（generated_by=rule，只针对事件型事实）
                res.beliefs.append({
                    "owner_name": speaker,
                    "kind": BELIEF_FACT,
                    "subject_kind": BELIEF_SUBJECT_EVENT,
                    "subject_ref": summary[:120],
                    "statement": "我记得：%s" % summary[:RULE_FACT_MAX_LEN],
                    "confidence": 0.9,
                    "generated_by": GENERATED_BY_RULE,
                    "based_on_event_index": event_index,
                    "source": mid,
                    "_source": EXTRACT_SOURCE_RULE,
                })

            # ---- 明确承诺 ----
            if hit_commit:
                res.commitments.append({
                    "promiser_name": speaker,
                    "promisee_name": None,
                    "content": text[:COMMITMENT_CONTENT_MAX_LEN],
                    "deadline": None,
                    "source_event_index": event_index,
                    "notes": "规则层命中：%s" % hit_commit,
                    "_source": EXTRACT_SOURCE_RULE,
                })

            # ---- 明确秘密 ----
            if hit_secret:
                res.secrets.append({
                    "owner_name": speaker,
                    "content": text[:SECRET_CONTENT_MAX_LEN],
                    "subject": "",
                    "source_event_index": event_index,
                    "_source": EXTRACT_SOURCE_RULE,
                })

            # ---- 情绪 -> 状态变化 ----
            if emotion_label:
                res.state_changes.append({
                    "character_name": speaker,
                    "field": "emotion",
                    "value": emotion_label,
                    "reason": text[:100],
                    "_source": EXTRACT_SOURCE_RULE,
                })

        # 规则层明确不产出：关系变化 / BELIEF / ATTITUDE / JUDGMENT
        res.relationship_changes = []
        res.beliefs = [b for b in res.beliefs if b.get("kind") == BELIEF_FACT]
        return res

    # ==================================================================
    # LLM 抽取
    # ==================================================================
    def _sanitize_belief(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """LLM 提案的信念消毒：FACT 一律降级为 BELIEF（FACT 只能来自规则层）。"""
        kind = str(raw.get("kind") or "").strip().upper()
        if kind == BELIEF_FACT:
            self.logger.warning(
                "[抽取] LLM 提出了 kind=FACT，已降级为 BELIEF（FACT 只能由规则层产出）")
            kind = BELIEF_BELIEF
        if kind not in LLM_WRITABLE_BELIEF_KINDS:
            self.logger.warning("[抽取] 丢弃非法 kind=%r 的 LLM 信念", raw.get("kind"))
            return None
        out = dict(raw)
        out["kind"] = kind
        out["generated_by"] = GENERATED_BY_LLM
        out["_source"] = EXTRACT_SOURCE_LLM
        return out

    def _sanitize_rel_change(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """LLM 提案的关系变化消毒：``|delta| > 0.5`` 直接丢弃。"""
        try:
            delta = float(raw.get("delta"))
        except Exception:
            self.logger.warning("[抽取] 丢弃 delta 非数值的关系变化：%r", raw.get("delta"))
            return None
        if delta != delta or abs(delta) > REL_MAX_DELTA:
            self.logger.warning(
                "[抽取] 丢弃 |delta|=%.3f 超上限 %.1f 的关系变化（%s -> %s）",
                abs(delta), REL_MAX_DELTA, raw.get("from_name"), raw.get("to_name"))
            return None
        field = str(raw.get("field") or "").strip().lower()
        if field not in ALLOWED_REL_FIELDS:
            self.logger.warning("[抽取] 丢弃非法关系字段 %r", raw.get("field"))
            return None
        out = dict(raw)
        out["field"] = field
        out["delta"] = delta
        out["_source"] = EXTRACT_SOURCE_LLM
        return out

    def _sanitize_visibility(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """可见性提案消毒：SUSPECTED/RUMORED 必须有非空 partial_content。"""
        state = str(raw.get("state") or "").strip().upper()
        if state == "UNKNOWN":
            self.logger.warning("[抽取] 丢弃 state=UNKNOWN 的可见性提案（不落库）")
            return None
        if state not in VALID_VISIBILITY_STATES:
            self.logger.warning("[抽取] 丢弃非法 state=%r 的可见性提案", raw.get("state"))
            return None
        partial = str(raw.get("partial_content") or "").strip()
        if state in VISIBILITY_NEEDS_PARTIAL and not partial:
            self.logger.warning(
                "[抽取] 丢弃 state=%s 但 partial_content 为空的可见性提案（角色=%s）",
                state, raw.get("character") or raw.get("name"))
            return None
        out = dict(raw)
        out["state"] = state
        out["partial_content"] = partial
        if "character" not in out:
            out["character"] = raw.get("name")
        out["_source"] = EXTRACT_SOURCE_LLM
        return out

    def _llm_extract(
        self,
        messages: Sequence[Any],
        mode: str = DEFAULT_MODE,
        roster: str = "",
    ) -> Optional[ExtractionResult]:
        """调 LLM 抽取；拿不到合法结果返回 None（由调用方回退规则）。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None

        msgs = self._normalize_messages(messages)
        if not msgs:
            return None
        candidates = self._build_memory_candidates(msgs)
        user_prompt = self._build_user_prompt(msgs, roster, candidates)
        if not user_prompt:
            self.logger.warning(
                "[抽取] 窗口里没有可抽取的正文（只剩客户端提示块 / 全被裁掉），"
                "跳过 LLM 抽取 → 退回规则模式")
            return None

        # [#41 10-05] user 泛称 → 玩家真名；并抹掉「（用户）」这个映射
        # 实测：PROMPT_SYSTEM 里「用户」只有 3 处，其中「【关于 user（用户）…】」
        # 就是把「user = 用户」直接教给模型的那一句，承诺文本里的「用户」由它而来。
        _user_name = ""
        try:
            _u_row = self.char_mgr.get_user() if self.char_mgr is not None else None
            if _u_row:
                _user_name = str(_u_row.get("name") or "").strip()
        except Exception:
            _user_name = ""
        if not _user_name:
            try:
                for _n in (getattr(getattr(self.config, "memory", None), "user_names", None) or ()):
                    _n_s = str(_n).strip()
                    if _n_s:
                        _user_name = _n_s
                        break
            except Exception:
                pass
        if _user_name:
            import re as _re
            _sys_p = PROMPT_SYSTEM.replace("（用户）", " ")
            _sys_p = _re.sub(r"(?<![A-Za-z0-9_])[Uu]ser(?![A-Za-z0-9_])",
                             lambda _m: _user_name, _sys_p)
            _sys_p = _sys_p.replace("用户", _user_name)
        else:
            _sys_p = PROMPT_SYSTEM
        raw = self.llm.chat_json(_sys_p, user_prompt,
                                 retries=LLM_DEFAULT_RETRIES)
        _dump_extract_debug(msgs, user_prompt, raw)
        if not isinstance(raw, dict):
            self.logger.warning("[抽取] LLM 未返回可用 JSON 对象")
            return None

        res = ExtractionResult(mode=str(mode), source=EXTRACT_SOURCE_LLM,
                               message_count=len(msgs))
        if "error" in raw and len(raw) == 1:
            res.error = str(raw.get("error"))
            return res

        # ---- events（含 participants -> 扁平 visibility）----
        for ev in _as_list(raw.get("events")):
            if not isinstance(ev, dict):
                continue
            if not str(ev.get("summary") or "").strip():
                res.warnings.append("丢弃无 summary 的事件")
                continue
            ev_out = dict(ev)
            idx = len(res.events)
            parts_out: List[Dict[str, Any]] = []
            for pt in _as_list(ev.get("participants")):
                if not isinstance(pt, dict):
                    continue
                vis = self._sanitize_visibility(pt)
                if vis is None:
                    continue
                vis["event_index"] = idx
                res.visibility_updates.append(vis)
                parts_out.append(pt)
            ev_out["participants"] = parts_out
            ev_out["source_message_ids"] = [
                str(x) for x in _as_list(ev.get("source_message_ids"))]
            ev_out["_source"] = EXTRACT_SOURCE_LLM
            res.events.append(ev_out)

        # ---- memories ----
        for mem in _as_list(raw.get("memories")):
            if not isinstance(mem, dict):
                continue
            if not str(mem.get("content") or "").strip():
                res.warnings.append("丢弃无 content 的记忆")
                continue
            mt = str(mem.get("memory_type") or DEFAULT_MEMORY_TYPE).strip().lower()
            if mt not in VALID_MEMORY_TYPES:
                self.logger.warning("[抽取] LLM 给出非法 memory_type=%r，回落 %s",
                                    mem.get("memory_type"), MEM_TYPE_EPISODIC)
                mt = MEM_TYPE_EPISODIC
            out = dict(mem)
            out["memory_type"] = mt
            out["_source"] = EXTRACT_SOURCE_LLM
            res.memories.append(out)

        # ---- beliefs（FACT 降级）----
        for bl in _as_list(raw.get("beliefs")):
            if not isinstance(bl, dict):
                continue
            if not str(bl.get("statement") or "").strip():
                res.warnings.append("丢弃无 statement 的信念")
                continue
            clean = self._sanitize_belief(bl)
            if clean is not None:
                res.beliefs.append(clean)

        # ---- commitments ----
        for cm in _as_list(raw.get("commitments")):
            if not isinstance(cm, dict):
                continue
            if not str(cm.get("content") or "").strip():
                res.warnings.append("丢弃无 content 的承诺")
                continue
            out = dict(cm)
            out["_source"] = EXTRACT_SOURCE_LLM
            res.commitments.append(out)

        # ---- secrets ----
        for sc in _as_list(raw.get("secrets")):
            if not isinstance(sc, dict):
                continue
            if not str(sc.get("content") or "").strip():
                res.warnings.append("丢弃无 content 的秘密")
                continue
            out = dict(sc)
            out["_source"] = EXTRACT_SOURCE_LLM
            res.secrets.append(out)

        # ---- relationship_changes（>0.5 丢弃）----
        for rc in _as_list(raw.get("relationship_changes")):
            if not isinstance(rc, dict):
                continue
            clean = self._sanitize_rel_change(rc)
            if clean is not None:
                res.relationship_changes.append(clean)

        # ---- state_changes ----
        for stc in _as_list(raw.get("state_changes")):
            if not isinstance(stc, dict):
                continue
            f = str(stc.get("field") or "").strip().lower()
            if f not in ALLOWED_STATE_FIELDS:
                if f in STATE_COMPAT_FIELDS:
                    self.logger.warning(
                        "[抽取] 丢弃写入 character_states.%s 的状态提案"
                        "（兼容字段，不作为关系真相源）", f)
                else:
                    self.logger.warning("[抽取] 丢弃非法 state 字段 %r", stc.get("field"))
                continue
            out = dict(stc)
            out["field"] = f
            out["_source"] = EXTRACT_SOURCE_LLM
            res.state_changes.append(out)

        # ---- knowledge_updates（event_id 强制 NULL）----
        for ku in _as_list(raw.get("knowledge_updates")):
            if not isinstance(ku, dict):
                continue
            if not str(ku.get("subject") or "").strip():
                res.warnings.append("丢弃无 subject 的知识更新")
                continue
            st = str(ku.get("status") or DEFAULT_KNOWLEDGE_STATUS).strip().upper()
            if st not in VALID_KNOWLEDGE_STATUSES:
                self.logger.warning("[抽取] 非法 knowledge.status=%r，回落 %s",
                                    ku.get("status"), DEFAULT_KNOWLEDGE_STATUS)
                st = DEFAULT_KNOWLEDGE_STATUS
            out = dict(ku)
            out["status"] = st
            if out.get("event_id") is not None:
                self.logger.warning(
                    "[抽取] 强制清除 knowledge_updates.event_id（事件型知识须走 "
                    "event_visibility）")
                out["event_id"] = None
            out["_source"] = EXTRACT_SOURCE_LLM
            res.knowledge_updates.append(out)

        # ---- 顶层 visibility_updates（与 participants 合并）----
        for vu in _as_list(raw.get("visibility_updates")):
            if not isinstance(vu, dict):
                continue
            clean = self._sanitize_visibility(vu)
            if clean is None:
                continue
            if "event_index" not in clean:
                clean["event_index"] = 0
            res.visibility_updates.append(clean)

        # 去重：同一 (event_index, character) 只留一条
        seen: set = set()
        deduped: List[Dict[str, Any]] = []
        for vu in res.visibility_updates:
            key = (_to_int(vu.get("event_index")),
                   str(vu.get("character") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(vu)
        res.visibility_updates = deduped

        return res


# ==============================================================================
# 22. TavoImporter —— JSONL 导入（幂等 + 增量）
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【15】Tavo 导入
# ══════════════════════════════════════════════════════════════════════

class TavoImporter:
    """Tavo / SillyTavern 聊天记录的导入器。

    * ``message_id = _sha(name|send_date|mes)`` —— schema 里 ``messages.message_id``
      是主键，所以**重复导入同一文件天然幂等**
    * 容错：单行 JSON 解析失败 -> 跳过该行并告警；缺 ``send_date`` / ``is_system``
      / ``name`` -> 兜底默认值；空消息 -> 跳过
    * 增量：新导入的行 ``processed = 0``，后续由 MemoryEngine 只处理未处理的
    """

    def __init__(
        self,
        db: Database,
        char_mgr: Optional[CharacterManager] = None,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.db = db
        self.char_mgr = char_mgr
        self.config = config
        self.logger = logger or _get_logger("importer")

    # ------------------------------------------------------------------
    def _iter_raw_records(self, path: Union[str, Path]) -> Iterator[Tuple[int, Any]]:
        """逐行读取，产出 ``(行号, 解析出的对象)``；解析失败的行产出 ``None``。"""
        p = Path(path)
        with p.open("r", encoding=DEFAULT_ENCODING, errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if not line or not line.strip():
                    continue
                if len(line) > TAVO_MAX_LINE_LEN:
                    yield lineno, None
                    continue
                try:
                    yield lineno, json.loads(line.strip())
                except Exception:
                    yield lineno, None

    def _expand_record(self, obj: Any) -> List[Dict[str, Any]]:
        """一行解析结果可能是单条、数组、或含 messages 的对象，统一展开。"""
        if isinstance(obj, dict):
            for key in ("messages", "chat", "history", "log"):
                inner = obj.get(key)
                if isinstance(inner, list):
                    return [x for x in inner if isinstance(x, dict)]
            return [obj]
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        return []

    def _normalize_record(
        self,
        obj: Dict[str, Any],
        position: int,
        source_file: str,
    ) -> Optional[Dict[str, Any]]:
        """归一化一条记录；不可用返回 None。"""
        name = _bounded_str(obj.get("name") or obj.get("speaker"), NAME_MAX_LEN)
        # 故意**不**兜底成 TAVO_DEFAULT_NAME：缺 name 的记录由 import_file 直接
        # 跳过，否则会在 characters 表里造出一个叫 "unknown" 的假角色。
        mes = obj.get("mes")
        if mes is None:
            mes = obj.get("content")
        if mes is None:
            mes = obj.get("text")
        text = str(mes if mes is not None else "")
        if not text.strip():
            return None

        is_user = 1 if obj.get("is_user") else 0
        is_system = 1 if obj.get("is_system") else 0
        send_date = obj.get("send_date")
        if send_date in (None, ""):
            send_date = obj.get("date")
        send_date_norm = _norm_iso(send_date, None)
        if send_date_norm is None:
            send_date_norm = now_iso()

        message_id = _sha("%s|%s|%s" % (name, send_date_norm, text))
        return {
            "message_id": message_id,
            "source_file": source_file,
            "source_position": int(position),
            "name": name,
            "is_user": is_user,
            "is_system": is_system,
            "mes": text,
            "send_date": send_date_norm,
        }

    # ------------------------------------------------------------------
    def import_file(
        self,
        path: Union[str, Path],
        auto_register: bool = True,
    ) -> Dict[str, Any]:
        """导入一个 JSONL / JSON 聊天记录文件。

        返回统计 dict：``total_lines`` / ``parsed`` / ``imported`` /
        ``skipped``（message_id 已存在）/ ``empty_skipped`` / ``bad_lines`` /
        ``characters`` / ``errors``。
        """
        p = Path(path)
        stats: Dict[str, Any] = {
            "path": str(p),
            "total_lines": 0,
            "parsed": 0,
            "imported": 0,
            "skipped": 0,
            "missing_name": 0,
            "empty_skipped": 0,
            "bad_lines": 0,
            "characters": [],
            "errors": [],
        }
        if not p.is_file():
            stats["errors"].append("文件不存在：%s" % p)
            self.logger.error("[导入] 文件不存在：%s", p)
            return stats

        source_file = p.name
        names: List[str] = []
        records: List[Dict[str, Any]] = []

        for lineno, obj in self._iter_raw_records(p):
            stats["total_lines"] += 1
            if obj is None:
                stats["bad_lines"] += 1
                self.logger.warning("[导入] 第 %d 行 JSON 解析失败，已跳过", lineno)
                continue
            expanded = self._expand_record(obj)
            if not expanded:
                stats["bad_lines"] += 1
                self.logger.warning("[导入] 第 %d 行结构无法识别，已跳过", lineno)
                continue
            for sub in expanded:
                stats["parsed"] += 1
                rec = self._normalize_record(sub, lineno, source_file)
                if rec is None:
                    stats["empty_skipped"] += 1
                    continue
                # 缺 name / name 为空：不落库、不注册角色、不计入 characters 名单
                if not rec.get("name"):
                    stats["skipped"] += 1
                    stats["missing_name"] += 1
                    self.logger.warning(
                        "[导入] 第 %d 行缺少 name 字段，已跳过（不创建占位角色）",
                        lineno)
                    continue
                records.append(rec)
                if rec["name"] not in names:
                    names.append(rec["name"])

        if auto_register and self.char_mgr is not None:
            for nm in names:
                self.char_mgr.get_or_create(nm)

        imported_at = now_iso()
        with self.db.transaction():
            for rec in records:
                if self.db.query_one(
                        "SELECT message_id FROM messages WHERE message_id = ?",
                        (rec["message_id"],)) is not None:
                    stats["skipped"] += 1
                    continue

                cid = None
                if self.char_mgr is not None:
                    cid = self.char_mgr.resolve_id(rec["name"])
                cur = self.db.execute(
                    "INSERT INTO messages "
                    "(message_id, source_file, source_position, name, is_user, "
                    " is_system, mes, send_date, character_id, imported_at, processed) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (rec["message_id"], rec["source_file"], rec["source_position"],
                     rec["name"], rec["is_user"], rec["is_system"], rec["mes"],
                     rec["send_date"], cid, imported_at))
                if cur is None:
                    stats["errors"].append("写入失败：%s" % rec["message_id"])
                    continue
                stats["imported"] += 1
                if cid is not None:
                    self.char_mgr.increment_message_count(cid, 1)

        stats["characters"] = names
        self.logger.info(
            "[导入] %s：行 %d / 解析 %d / 新增 %d / 跳过(重复) %d / 空消息 %d / 坏行 %d",
            source_file, stats["total_lines"], stats["parsed"], stats["imported"],
            stats["skipped"], stats["empty_skipped"], stats["bad_lines"])
        return stats

    # ------------------------------------------------------------------
    def pending_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """取 ``processed = 0`` 的待抽取消息（按文件内位置排序）。"""
        sql = ("SELECT * FROM messages WHERE processed = 0 "
               "ORDER BY source_file ASC, source_position ASC, rowid ASC")
        params: List[Any] = []
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.db.query(sql, tuple(params))

    def mark_processed(self, message_ids: Sequence[Any]) -> int:
        """把消息标记为已处理，返回更新条数。"""
        ids = [str(x) for x in (message_ids or []) if str(x).strip()]
        if not ids:
            return 0
        marks = ", ".join("?" * len(ids))
        cur = self.db.execute(
            f"UPDATE messages SET processed = 1 WHERE message_id IN ({marks})",
            tuple(ids))
        return len(ids) if cur is not None else 0

    def unprocessed_count(self) -> int:
        """待抽取消息数。"""
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM messages WHERE processed = 0", (), 0) or 0)

    def message_count(self) -> int:
        """消息总数。"""
        return self.db.count("messages")


# ==============================================================================
# 23. ContextBuilder —— 生成角色上下文 + Stance 推导
# ==============================================================================

# ══════════════════════════════════════════════════════════════════════
# 【16】上下文组装
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Block:
    """§11.6 注入块：A 阶段只装 kind/lines，B 阶段再加 priority/layer。"""
    kind: str
    lines: List[str]


ME_BLOCK_HEADER = """【本段说明 · 优先级】

以下按重要性从高到低提供你的信息：

  第一层 · 你是谁 —— 不可更改
  第二层 · 此刻现实 —— 比过去的设定优先
  第三层 · 你的内心与认知 —— 你记得 / 相信 / 想要的

消息列表里还有其他内容：
  · 你和对方的历史对话 = 之前说过什么
  · 世界书 / 角色卡原始设定 = 开局背景

【冲突判定】
若以上内容互相矛盾，一律以本段 1→2→3 的顺序为准。
世界书里的旧设定已被本段的当下现实覆盖。

"""

KIND_PRIORITY = {
    "identity": 1,
    "stance": 2,
    "continuity": 3,
    "presence": 4,
    "scene": 5,
    "time_aware": 8,
    "user": 9,
    "relation": 10,
    "state": 11,
    "belief": 12,
    "commitment": 13,
    "memory": 20,
    "secret": 21,
    "time": 30,
}
# §11.6-B：超预算时可整块丢弃的 kind。其余为保留块（仅硬切兜底）。
KIND_DROPPABLE = frozenset({"relation", "state", "belief", "commitment", "memory", "secret", "time"})


class ContextBuilder:
    """为某个角色拼装供 LLM 使用的上下文文本。

    **硬约束（SPEC 原则 7 / 8）**：

    * 绝不输出 ``【你不知道的事情】`` 之类的区块 —— 那本身就是信息泄露
    * 只加载**当前角色自己**的 memories / knowledge / beliefs /
      relationships / visibility / commitments / secrets
    * 其他角色的私密记忆、其他角色才知道的 knowledge，一律不出现
    * 输出末尾由 ``_sanitize`` 兜底扫描 ``FORBIDDEN_CONTEXT_MARKERS``，
      命中即替换并 ``logging.error``

    Stance 由 ``_derive_stance`` **实时推导，不写数据库**（SPEC 强制约束 10）。
    """

    def __init__(
        self,
        char_mgr: CharacterManager,
        mem_mgr: MemoryManager,
        rel_mgr: RelationshipManager,
        state_mgr: StateManager,
        know_mgr: KnowledgeManager,
        commit_mgr: CommitmentManager,
        secret_mgr: SecretManager,
        belief_mgr: BeliefManager,
        vis_mgr: VisibilityManager,
        config: Optional[Config] = None,
        llm: Optional[LLMClient] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.char_mgr = char_mgr
        self.mem_mgr = mem_mgr
        self.rel_mgr = rel_mgr
        self.state_mgr = state_mgr
        self.know_mgr = know_mgr
        self.commit_mgr = commit_mgr
        self.secret_mgr = secret_mgr
        self.belief_mgr = belief_mgr
        self.vis_mgr = vis_mgr
        self.config = config
        self.llm = llm
        self.logger = logger or _get_logger("context")

    # ==================================================================
    # 工具
    # ==================================================================
    @staticmethod
    def _time_anchor(created_at: Any) -> str:
        """按 created_at 算相对时间前缀（形如「今天，」）。解析失败返回空串。"""
        from datetime import datetime, timezone
        if not created_at:
            return ""
        try:
            s = str(created_at).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            t = datetime.fromisoformat(s)
            now = datetime.now(timezone.utc) if t.tzinfo else datetime.now()
            h = (now - t).total_seconds() / 3600.0
        except Exception:
            return ""
        if h < 6:
            return "刚才，"
        if h < 24:
            return "今天，"
        if h < 72:
            return "前几天，"
        if h < 720:
            return "前些日子，"
        return "很久以前，"

    @staticmethod
    def _sanitize(text: str) -> str:
        """兜底安全过滤：禁字样出现即替换 + error 日志。"""
        out = text
        for marker in FORBIDDEN_CONTEXT_MARKERS:
            if marker in out:
                _get_logger("context").error(
                    "[上下文] 检测到禁字样 %r，已强制移除（这是信息泄露，属 bug）",
                    marker)
                out = out.replace(marker, "（该区块已按规范移除）")
        return out

    def _rel_summary(self, r: Dict[str, Any]) -> str:
        """把一条关系行压成一句中文摘要（``_rel_summary``）。

        [relations-5] 档位判定走 ``_rel_band``（带滞后带），数值在阈值附近
        抖动时注入句子不跟着来回跳。**只影响措辞，不回写数据库。**
        """
        if r is None:
            return "（无记录）"
        if r.get("state_summary"):
            return str(r["state_summary"])
        _bk = r.get("rel_id")
        if _bk is None:
            _bk = "%s>%s" % (r.get("from_character_id"),
                             r.get("to_character_id"))
        parts: List[str] = []
        # [relations-3] 措辞表：自然短句，不带任何括号数值。
        #   (字段, 高档阈值, 低档阈值, 高档措辞, 低档措辞)
        #   低档阈值为 -1 / 低档措辞为 None -> 该维度不产出"低"措辞。
        pairs = (
            (REL_TRUST, 0.65, 0.30, "你比较信任他", "你不完全信任他"),
            (REL_AFFECTION, 0.65, 0.30, "你对他有好感", "你对他没什么好感"),
            (REL_RESPECT, 0.65, 0.30, "你敬重他", None),
            (REL_FAMILIARITY, 0.70, 0.25, "你和他很熟", None),
            (REL_DEPENDENCY, 0.60, -1, "你依赖他", None),
        )
        for f, hi, lo, hi_txt, lo_txt in pairs:
            v = _clamp(r.get(f), 0.0, 1.0, 0.5)
            band = _rel_band("%s|%s" % (_bk, f), v, hi, lo)
            if band == 2:
                parts.append(hi_txt)
            elif band == 1 and lo_txt:
                parts.append(lo_txt)
        for f, hi_txt in ((REL_RESENTMENT, "你心里有怨气"),
                          (REL_FEAR, "你有些忌惮他")):
            v = _clamp(r.get(f), 0.0, 1.0, 0.0)
            if _rel_band("%s|%s" % (_bk, f), v, 0.40, -1) == 2:
                parts.append(hi_txt)
        return "；".join(parts) if parts else "关系平淡，无明显倾向"

    def _resolve_user(self, cid: int,
                      user_character: Any = None) -> Optional[Dict[str, Any]]:
        """确定"与你对话的人"是谁。"""
        if user_character is not None:
            row = self.char_mgr.get(user_character)
            if row is not None and int(row["character_id"]) != int(cid):
                return row
        row = self.char_mgr.get_user()
        if row is not None and int(row["character_id"]) != int(cid):
            return row
        # 退路：找一个不是自己的角色
        for r in self.char_mgr.all():
            if int(r["character_id"]) != int(cid):
                return r
        return None

    # ==================================================================
    # 分区
    # ==================================================================
    def _role_block(self, char: Dict[str, Any]) -> List[str]:
        """【你是】/【角色类型】/ static_profile 各字段。"""
        lines = [
            "【你是】%s" % char.get("name"),
            "【角色类型】%s" % (char.get("role_type") or ROLE_UNKNOWN),
        ]
        static = _as_dict(char.get("static_profile"))
        for k, v in static.items():
            if v in (None, "", [], {}):
                continue
            if isinstance(v, (list, tuple)):
                lines.append("【%s】%s" % (k, "、".join(str(x) for x in v)))
            elif isinstance(v, dict):
                lines.append("【%s】%s" % (
                    k, "；".join("%s=%s" % (kk, vv) for kk, vv in v.items())))
            else:
                lines.append("【%s】%s" % (k, v))
        traits = self.char_mgr.get_traits(char["character_id"])
        if traits:
            lines.append("【性格特征】%s" % "、".join(traits))
        return lines

    def _relation_anchors(self, cid: int, uid: int,
                          want: int = ANCHOR_MAX_ITEMS) -> List[str]:
        """[relations-2] A→B 最近的关系变更 -> 事件证据短句列表。"""
        try:
            rows = self.rel_mgr.get_recent_history(cid, uid,
                                                   limit=ANCHOR_FETCH_LIMIT)
        except Exception as ex:
            self.logger.warning("[上下文] 取关系历史失败（忽略）：%s", ex)
            return []
        out: List[str] = []
        seen: List[str] = []
        for r in (rows or []):
            txt = self._anchor_text(r.get("reason"))
            if not txt or txt in seen:
                continue
            seen.append(txt)
            out.append(txt)
            if len(out) >= want:
                break
        return out

    @staticmethod
    def _anchor_text(reason: Any) -> str:
        """[relations-2] reason -> 合格 anchor 短句；不合格返回空串。"""
        s = str(reason or "").strip()
        if not s:
            return ""
        if len(s) > ANCHOR_REASON_MAX_LEN:
            head = s
            for sep in ANCHOR_SENTENCE_SEPS:
                pos = s.find(sep)
                if pos != -1:
                    head = s[:pos]
                    break
            s = head.strip()
        if len(s) < ANCHOR_MIN_LEN:
            return ""
        return s

    def _attitude_line(self, cid: int, user_row: Dict[str, Any]) -> str:
        """由 **relationships 数值摘要 + ATTITUDE beliefs** 组合成一句自然语言。

        明确**不读** ``relationships.state_summary``：本引擎没有任何代码路径
        依赖它（写了也不会显示），读它只会让这一行永远空着。
        改为现场用 ``_rel_summary(rel)`` 从 7 个数值字段生成摘要。
        """
        uname = str(user_row.get("name") or "")
        uid = int(user_row["character_id"])
        segs: List[str] = []

        # ---- 1) relationships（数值型摘要）----
        rel = self.rel_mgr.get(cid, uid)
        if rel is not None:
            rel_sum = self._rel_summary(rel)
            if rel_sum and rel_sum != "（无记录）":
                segs.append(rel_sum.rstrip("。"))

        # ---- 2) ATTITUDE beliefs（只取针对该 user 的）----
        atts = self.belief_mgr.list_for(cid, kind=BELIEF_ATTITUDE,
                                        limit=CONTEXT_BELIEF_LIMIT)
        stmts: List[str] = []
        for a in atts:
            ref = str(a.get("subject_ref") or "").strip()
            if ref and ref != uname:
                continue
            s = str(a.get("statement") or "").strip().rstrip("。")
            if s and s not in stmts:
                stmts.append(s)
            if len(stmts) >= 2:
                break
        segs.extend(stmts)

        if not segs:
            return "（暂无明确态度）"
        return "；".join(segs) + "。"

    def _user_block(
        self,
        cid: int,
        user_char: Optional[Dict[str, Any]],
        current_message: str = "",
    ) -> List[str]:
        """「关于用户」整块（``_user_block``）。"""
        if user_char is None:
            return ["====== 关于用户 ======",
                    "【用户】（本会话未识别出人类角色）"]
        uname = str(user_char.get("name") or "")
        uid = int(user_char["character_id"])
        out: List[str] = ["====== 关于用户「%s」 ======" % uname,
                          "【用户】%s（这是与你对话的人）" % uname,
                          "【你对%s的态度】%s" % (uname, self._attitude_line(cid, user_char))]
        # [relations-2] 事件证据 anchor：没有合格 anchor 就整段不输出
        anchors = self._relation_anchors(cid, uid)
        if anchors:
            out.append("【你和%s之间最近发生的事】" % uname)
            for _a in anchors:
                out.append("  · %s" % _a)

        # 该角色视角下与 user 相关的记忆
        mems = self.mem_mgr.retrieve(cid, query=uname or current_message,
                                     limit=CONTEXT_MEMORY_LIMIT)
        rel_mems = [m for m in mems
                    if uname and uname in str(m.get("content") or "")]
        if not rel_mems:
            rel_mems = mems[:CONTEXT_STANCE_MEMORY_LIMIT]
        out.append("【你和%s之间发生过的事】" % uname)
        if rel_mems:
            for m in rel_mems:
                out.append("  - %s%s" % (
                    self._time_anchor(m.get("created_at")),
                    m.get("content")))
        else:
            out.append("  （暂无）")

        # 从 user 那里知道的非事件型事实
        known = self.know_mgr.get_by_subject(cid, uname, statuses=[KN_KNOWN])
        out.append("【你从%s那里知道的事】" % uname)
        if known:
            for k in known[:CONTEXT_MEMORY_LIMIT]:
                out.append("  - %s" % k.get("subject"))
        else:
            out.append("  （暂无）")

        # 关于 user 的怀疑 / 听说
        sus = self.know_mgr.get_by_subject(
            cid, uname, statuses=[KN_SUSPECTED, KN_RUMORED])
        out.append("【关于%s你怀疑或听说过的】" % uname)
        if sus:
            for k in sus[:CONTEXT_MEMORY_LIMIT]:
                out.append("  - （%s）%s" % (k.get("status"), k.get("subject")))
        else:
            out.append("  （暂无）")

        # 与 user 之间未完成的承诺
        commits = self.commit_mgr.list_between(cid, uid,
                                                list(COMMITMENT_OPEN_STATUSES))
        out.append("【你和%s之间的未完成承诺】" % uname)
        if commits:
            for cm in commits[:CONTEXT_COMMITMENT_LIMIT]:
                who = ("你答应" if int(cm["promiser_id"]) == int(cid)
                       else "%s答应" % (cm.get("promiser_name") or "对方"))
                dl = ("，期限 %s" % cm["deadline"]) if cm.get("deadline") else ""
                out.append("  - %s：%s（%s）%s"
                           % (who, cm.get("content"), cm.get("status"), dl))
        else:
            out.append("  （暂无）")
        return out

    # ==================================================================
    # Stance（实时推导，不落库）
    # ==================================================================
    def _derive_stance(
        self,
        cid: int,
        user_id: Optional[int],
        current_message: str = "",
    ) -> str:
        """综合 6 个输入，生成一句自然语言行动倾向（**不写数据库**）。

        输入（SPEC 第 10 条）：

        1. 该角色对该 user 的 top ``ATTITUDE`` beliefs
        2. 最近 3~5 条相关 memories
        3. ``relationships`` 数值
        4. ``character_states`` 当前状态
        5. active ``commitments``（该角色与 user 之间）
        6. ``current_message``

        规则模板生成；若注入了可用的 ``LLMClient``，可做一次自然语言润色
        （失败自动回退模板，且**任何情况下都不落库**）。
        """
        segs: List[str] = []
        uname = ""
        if user_id is not None:
            urow = self.char_mgr.get(user_id)
            uname = str(urow.get("name")) if urow else ""

        # ---- 1) ATTITUDE beliefs + 3) relationships（两者组合，不是二选一）----
        #      注意：这里用 get() 而非 get_or_create() —— SPEC 强制约束 10 要求
        #      "Stance 不落库"，Stance 推导路径不得产生任何数据库写入。
        atts = self.belief_mgr.list_for(cid, kind=BELIEF_ATTITUDE,
                                        limit=CONTEXT_BELIEF_LIMIT)
        attitude_txt = ""
        for a in atts:
            ref = str(a.get("subject_ref") or "").strip()
            if uname and ref and ref != uname:
                continue
            attitude_txt = str(a.get("statement") or "").strip().rstrip("。")
            if attitude_txt:
                break

        # ---- 3) 关系数值 ----
        trust = aff = res = fear = 0.5
        rel_row: Optional[Dict[str, Any]] = None
        if user_id is not None:
            rel_row = self.rel_mgr.get(cid, user_id)
            if rel_row is not None:
                trust = _clamp(rel_row.get(REL_TRUST), 0.0, 1.0, 0.5)
                aff = _clamp(rel_row.get(REL_AFFECTION), 0.0, 1.0, 0.5)
                res = _clamp(rel_row.get(REL_RESENTMENT), 0.0, 1.0, 0.0)
                fear = _clamp(rel_row.get(REL_FEAR), 0.0, 1.0, 0.0)

        if attitude_txt:
            segs.append(attitude_txt)
        elif trust <= 0.35:
            segs.append("你不完全相信他")
        elif trust >= 0.7:
            segs.append("你比较信任他")
        else:
            segs.append("你对他保持观望")

        # 关系数值摘要与 ATTITUDE 陈述并列贡献，共同构成"态度"
        if rel_row is not None and _rel_row_should_emit(rel_row):
            rel_sum = self._rel_summary(rel_row)
            if rel_sum and rel_sum not in ("关系平淡，无明显倾向", "（无记录）"):
                segs.append(rel_sum.rstrip("。"))

        if res >= 0.4:
            segs.append("心里还有未消的怨气")
        if fear >= 0.4:
            segs.append("对他有些忌惮")

        # ---- 5) active commitments ----
        pending: List[str] = []
        if user_id is not None:
            for cm in self.commit_mgr.list_between(cid, user_id,
                                                   [COMMITMENT_ACTIVE]):
                if int(cm.get("promiser_id") or 0) == int(cid):
                    pending.append("你答应过%s" % (cm.get("content") or ""))
                else:
                    pending.append("他答应过%s" % (cm.get("content") or ""))
        if pending:
            segs.append("但你还记得" + "、".join(str(x).rstrip("。，,. ") for x in pending[:2]))

        # ---- 4) character_states ----
        st = self.state_mgr.get(cid)
        if st:
            mood = st.get("emotion") or st.get("mood")
            stress = _clamp(st.get("stress"), 0.0, 1.0, 0.0)
            anger = _clamp(st.get("anger"), 0.0, 1.0, 0.0)
            if mood:
                segs.append("你现在的心情是「%s」" % mood)
            if stress >= 0.5 or anger >= 0.5:
                segs.append("而且情绪正绷着")

        # ---- 2) 最近相关 memories ----
        mems = self.mem_mgr.retrieve(cid, query=current_message or uname,
                                     limit=CONTEXT_STANCE_MEMORY_LIMIT)
        if mems:
            top = str(mems[0].get("content") or "").strip()
            if top:
                segs.append("你脑子里最先浮起的是「%s」" % top[:60])

        # ---- 6) current_message ----
        if str(current_message or "").strip():
            segs.append("面对他刚说的话，你打算谨慎应对")
        else:
            segs.append("你打算先按自己的节奏来")

        return "，".join(segs) + "。"

    # ==================================================================
    # 主入口
    # ==================================================================
    def build(
        self,
        character: Any,
        current_message: str = "",
        debug: bool = False,
        user_character: Any = None,
        time_aware: bool = False,
        time_now: Any = "",
        time_prev: Any = None,
        present_names: Optional[List[str]] = None,
        scene_state: Optional[Dict[str, Any]] = None,
        story_time: str = "",
    ) -> str:
        """生成该角色的完整上下文文本。

        ``debug=True`` 时在每个记忆条目后附加打分明细。

        **V5.6**：``time_aware=True``（这张卡的开场白带 ``【时间感知】开``）
        时，在输出**最前面**加两行 ``【当前时间】`` / ``【距上次对话】``；
        默认 False —— 跟改造前完全一样，一个字都不加。
        """
        cid = self.char_mgr.resolve_id(character)
        if cid is None:
            return "（未找到角色：%s）" % character
        char = self.char_mgr.get(cid)
        if char is None:
            return "（未找到角色：%s）" % character

        mcfg = self.config.memory if self.config is not None else MemoryConfig()
        user_row = self._resolve_user(cid, user_character)
        uid = int(user_row["character_id"]) if user_row else None

        # [relations-8] 本轮计数（必须在注入任何关系之前自增）
        try:
            _rel_turn_bump()
        except Exception:
            pass
        blocks: List[Block] = []

        # ---- 1. 角色本体 ----
        lines: List[str] = []
        lines.extend(self._role_block(char))
        lines.append("")

        blocks.append(Block(kind="identity", lines=lines))
        # ---- 0. V5.6：时间感知（按卡开关，只在这张卡开了的时候才加）----
        lines: List[str] = []
        if time_aware:
            lines.extend(_time_block_lines(time_now, time_prev))

        blocks.append(Block(kind="time_aware", lines=lines))
        # ---- 0b. 本轮在场名单（空/None 时一段都不输出）----
        lines: List[str] = []
        logging.getLogger(APP_NAME).info("[注入] 本轮在场=%s", present_names)
        if present_names:
            lines.append("")
            lines.append("【本轮在场】")
            lines.append("这一场戏里出现的角色：%s。"
                         % "、".join(present_names))
            lines.append("不在场的人此刻在做自己的事，"
                         "不要让他们听到或评论这场对话。")

        blocks.append(Block(kind="presence", lines=lines))
        # ---- 0d. 剧情时间（有才输出）----
        lines: List[str] = []
        if story_time:
            lines.append("")
            lines.append("【当前剧情时间】%s" % story_time)
            lines.append("")

        blocks.append(Block(kind="time", lines=lines))
        # ---- 0c. 场景状态（有才输出）----
        lines: List[str] = []
        try:
            _locs = (scene_state or {}).get("locations") or {}
            _acts = (scene_state or {}).get("actions") or {}
            if _locs:
                lines.append("")
                lines.append("【各角色当前位置】")
                for _nm, _loc in _locs.items():
                    lines.append("- %s：%s" % (_nm, _loc))
            if _acts:
                lines.append("")
                lines.append("【各角色当前状态】")
                for _nm, _act in _acts.items():
                    lines.append("- %s：%s" % (_nm, _act))
            if _locs or _acts:
                lines.append("")
                lines.append("不在同一地点的角色无法直接互动；"
                             "一个地点发生的事，其它地点的角色不知道。")
        except Exception:
            pass
        blocks.append(Block(kind="scene", lines=lines))
        # ---- 4. 当前状态 ----
        lines: List[str] = []
        st = self.state_mgr.get(cid)
        lines.append("【当前状态】%s" % (st.get("summary") if st and st.get("summary")
                                    else "（暂无状态摘要）"))
        detail_bits: List[str] = []
        if st:
            for f in ("emotion", "mood", "current_location", "current_goal"):
                if st.get(f):
                    detail_bits.append("%s=%s" % (f, st[f]))
            for f in ("anger", "fear", "stress"):
                v = _clamp(st.get(f), 0.0, 1.0, 0.0)
                if v > 0.01:
                    detail_bits.append("%s=%.2f" % (f, v))
        lines.append("【状态细节】%s" % ("，".join(detail_bits) if detail_bits else "—"))
        lines.append("")

        blocks.append(Block(kind="state", lines=lines))
        # ---- 2. 关于用户 ----
        lines: List[str] = []
        lines.extend(self._user_block(cid, user_row, current_message))
        lines.append("")

        blocks.append(Block(kind="user", lines=lines))
        # ---- 3. 与其他角色的关系 ----
        lines: List[str] = []
        # [relations-8] 强状态周期性重申（轮次已在 build() 开头自增）
        lines.append("【你与其他角色的关系】")
        rels = [r for r in self.rel_mgr.list_for(cid, "out")
                if uid is None or int(r["to_character_id"]) != uid]
        _rel_emit = [r for r in rels if _rel_row_should_emit(r)]
        if _rel_emit:
            for r in _rel_emit:
                lines.append("  - 对%s：%s" % (r.get("to_name"), self._rel_summary(r)))
        else:
            lines.append("  （暂无）")
        lines.append("")

        blocks.append(Block(kind="relation", lines=lines))
        # ---- 6. 三类信念 ----
        lines: List[str] = []
        for header, kd in (("【你相信的事】", BELIEF_BELIEF),
                           ("【你对某人的态度】", BELIEF_ATTITUDE),
                           ("【你对自己的看法】", BELIEF_SELF_BELIEF)):
            lines.append(header)
            bs = self.belief_mgr.list_for(cid, kind=kd, limit=CONTEXT_BELIEF_LIMIT)
            if bs:
                for b in bs:
                    ref = ("（%s）" % b["subject_ref"]) if b.get("subject_ref") else ""
                    lines.append("  - %s%s" % (b.get("statement"), ref))
            else:
                lines.append("  （暂无）")
        lines.append("")

        blocks.append(Block(kind="belief", lines=lines))
        # ---- 7. 未完成的承诺 ----
        lines: List[str] = []
        lines.append("【未完成的承诺】")
        commits = self.commit_mgr.list_for_character(
            cid, list(COMMITMENT_OPEN_STATUSES))
        if commits:
            for cm in commits[:CONTEXT_COMMITMENT_LIMIT]:
                mine = int(cm.get("promiser_id") or 0) == int(cid)
                if mine:
                    tgt = cm.get("promisee_name") or "（未指定对象）"
                    lines.append("  - 你答应%s：%s" % (tgt, cm.get("content")))
                else:
                    lines.append("  - %s答应你：%s"
                                 % (cm.get("promiser_name") or "对方", cm.get("content")))
        else:
            lines.append("  （暂无）")
        lines.append("")

        blocks.append(Block(kind="commitment", lines=lines))
        # ---- 8. 你的秘密 ----
        lines: List[str] = []
        lines.append("【你的秘密】")
        secrets = self.secret_mgr.list_active(cid)
        if secrets:
            for s in secrets[:CONTEXT_SECRET_LIMIT]:
                subj = ("（关于%s）" % s["subject"]) if s.get("subject") else ""
                lines.append("  - %s%s" % (s.get("content"), subj))
        else:
            lines.append("  （暂无）")
        lines.append("")

        blocks.append(Block(kind="secret", lines=lines))
        # ---- 5. 其他重要记忆（V6 阶段C：Token 预算分配）----
        lines: List[str] = []
        # 废除旧的两道硬编码：``max_context_memories=20`` 条 + ``CONTEXT_MEMORY_LIMIT=8``
        # 条 + 整份文本 6000 字截断。改为：
        #   * 先多取一些候选（retrieve 自带排序 + 休眠唤醒）
        #   * 再按 memory.context_token_budget 做 Token 预算分配
        #     （tier1 优先注入，剩余 40%/30%/20% 分给 tier2/3/4）
        # 预算设为 <=0 时退回旧的「按条数取」行为（可一键回滚）。
        lines.append("【其他重要记忆】")
        _budget = int(getattr(mcfg, "context_token_budget",
                              CONTEXT_TOKEN_BUDGET) or 0)
        if _budget > 0:
            _cand_limit = max(int(mcfg.max_context_memories or 0), 60)
            mems = self._select_memories_by_budget(
                self.mem_mgr.retrieve(cid, query=current_message,
                                      limit=_cand_limit, debug=debug),
                _budget)
        else:
            mems = self.mem_mgr.retrieve(
                cid, query=current_message, limit=mcfg.max_context_memories,
                debug=debug)
        injected_ids: List[int] = []
        for m in mems:
            if uid is not None and user_row is not None:
                uname = str(user_row.get("name") or "")
                if uname and uname in str(m.get("content") or ""):
                    continue
            tail = ""
            if debug and m.get("_debug"):
                tail = "  " + str(m["_debug"])
            _st_v = str(m.get("story_time") or "").strip()
            if _st_v:
                _prefix = "（%s）" % _st_v
            else:
                _prefix = self._time_anchor(m.get("created_at"))
            lines.append("  - %s%s%s" % (_prefix, m.get("content"), tail))
            _mid = _to_int(m.get("memory_id"))
            if _mid is not None:
                injected_ids.append(_mid)
        if not injected_ids:
            lines.append("  （暂无）")
        # [V6 阶段C] 被注入 Prompt 的记忆：consolidation += 0.05（衰减更慢）
        if injected_ids and bool(getattr(mcfg, "consolidation_bump", True)):
            try:
                self.mem_mgr.bump_consolidation(injected_ids)
            except Exception as ex:
                self.logger.warning("[上下文] 累加巩固度失败（忽略）：%s", ex)
        lines.append("")

        blocks.append(Block(kind="memory", lines=lines))
        # ---- 9. Stance ----
        lines: List[str] = []
        lines.append("【当前行为倾向】%s" % self._derive_stance(cid, uid, current_message))
        lines.append("")

        blocks.append(Block(kind="stance", lines=lines))
        # ---- 10. 角色连续性要求 ----
        lines: List[str] = []
        lines.append("【角色连续性要求】")
        for s in CONTEXT_SAFETY_LINES:
            lines.append("- %s" % s)

        blocks.append(Block(kind="continuity", lines=lines))
        text = ME_BLOCK_HEADER + self.assemble(blocks, mcfg)
        return self._sanitize(text)

    # ==================================================================
    # [V6 阶段C] 记忆注入的 Token 预算分配
    # ==================================================================
    def assemble(self, blocks: List["Block"], mcfg: Any) -> str:
        """§11.6-B：priority 升序重排；超预算时从尾部裁 droppable 块。"""
        _indexed = list(enumerate(blocks))
        _indexed.sort(key=lambda x: (KIND_PRIORITY.get(x[1].kind, 999), x[0]))
        _ordered = [b for _, b in _indexed]

        def _render(bs):
            return "\n".join(l for b in bs for l in b.lines)

        _max = int(getattr(mcfg, "context_max_chars", CONTEXT_MAX_CHARS_DEFAULT)
                   or CONTEXT_MAX_CHARS_DEFAULT)
        _text = _render(_ordered)

        if len(_text) <= _max:
            self.logger.info(
                "[B-审计] 顺序=%s 总长=%d 预算=%d",
                ",".join(b.kind for b in _ordered), len(_text), _max)
            return _text

        _keep = list(_ordered)
        _dropped = []
        while _keep:
            _text = _render(_keep)
            if len(_text) <= _max:
                break
            _di = -1
            for _i in range(len(_keep) - 1, -1, -1):
                if _keep[_i].kind in KIND_DROPPABLE:
                    _di = _i
                    break
            if _di < 0:
                break
            _dropped.append(_keep.pop(_di).kind)

        if _dropped:
            self.logger.info("[B-裁剪] 丢弃 %d 块：%s", len(_dropped), ",".join(_dropped))

        _text = _render(_keep)
        if len(_text) > _max:
            _cut_preview = _text[_max:][:200].replace("\n", " ")
            self.logger.warning(
                "[B-裁剪] 核心块超预算，硬切。被切开头：%r", _cut_preview)
            _text = _text[:_max]

        self.logger.info(
            "[B-审计] 顺序=%s 总长=%d 预算=%d 丢=%d",
            ",".join(b.kind for b in _keep), len(_text), _max, len(_dropped))
        return _text

    @staticmethod
    def _est_tokens(text: Any) -> int:
        """粗略 Token 估算（不引第三方库）。

        * 汉字 / 全角标点：1 字 ≈ 1 token
        * 其余（拉丁 / 数字 / 空白）：4 字符 ≈ 1 token
        * 空文本算 1（每条记忆自带的前缀开销另计）
        """
        s = str(text or "")
        cjk = 0
        other = 0
        for ch in s:
            if '\u2e80' <= ch <= '\u9fff' or '\uf900' <= ch <= '\ufaff' \
                    or '\uff00' <= ch <= '\uffef' or '\u3000' <= ch <= '\u303f':
                cjk += 1
            else:
                other += 1
        return max(1, cjk + (other + 3) // 4)

    def _select_memories_by_budget(
        self,
        mems: Sequence[Dict[str, Any]],
        budget: int,
    ) -> List[Dict[str, Any]]:
        """[V6 阶段C] 按 Token 预算挑记忆，**废除「最多 20 条 / 6000 字」**。

        分配规则（``memory.context_token_budget`` 为总预算）：

        1. **tier1（身份 / 核心关系 / 不可逆事件）优先注入**：不参与比例
           分配，按得分倒序塞满整个预算（塞不下才停）。
        2. 剩余预算按 **40% / 30% / 20%** 分配给 tier2 / tier3 / tier4
           （合计 90%，留 10% 余量，避免把窗口塞爆）。
        3. 某一档用不完的预算**不回收**给下一档（保持各档上限可预测）；
           预算小于单条成本时，该档直接不注入。
        4. 输出顺序 = tier1 -> tier2 -> tier3 -> tier4（核心记忆排最前，
           模型先读到最重要的）。

        ``budget <= 0`` 时退回「按原来的条数上限」行为（由调用方处理）。
        """
        total = max(0, int(budget or 0))
        if total <= 0 or not mems:
            return list(mems or [])
        # 每条记忆的固定开销（"  - [type] " 前缀 + 换行）
        overhead = 8
        buckets: Dict[int, List[Dict[str, Any]]] = {
            TIER_CORE: [], TIER_IMPORTANT: [], TIER_NORMAL: [],
            TIER_TRANSIENT: [],
        }
        for m in mems:
            t = _to_int(m.get("tier"))
            if t not in buckets:
                t = DEFAULT_TIER
            buckets[t].append(m)

        picked: List[Dict[str, Any]] = []
        used = 0

        def _cost(mem: Dict[str, Any]) -> int:
            return overhead + self._est_tokens(mem.get("content"))

        def _fill(items: List[Dict[str, Any]], cap: int) -> int:
            """往 picked 里塞，直到超过 cap 或塞完；返回本次用掉的 token。"""
            spent = 0
            for mem in items:
                c = _cost(mem)
                if spent + c > cap:
                    continue        # 预算不够就跳过这条，继续看更小的
                picked.append(mem)
                spent += c
            return spent

        # 1) tier1 优先，吃整个预算
        used += _fill(buckets[TIER_CORE], total)
        remain = max(0, total - used)
        # 2) 剩余按 40/30/20 分给 tier2/3/4
        for tier, ratio in ((TIER_IMPORTANT, TIER_BUDGET_RATIO[2]),
                            (TIER_NORMAL, TIER_BUDGET_RATIO[3]),
                            (TIER_TRANSIENT, TIER_BUDGET_RATIO[4])):
            cap = int(remain * ratio)
            if cap <= 0:
                continue
            _fill(buckets[tier], cap)
        self.logger.info(
            "[上下文] Token 预算分配：预算=%d 实选=%d 条(用 %d token) "
            "分档 tier1=%d tier2=%d tier3=%d tier4=%d",
            total, len(picked),
            sum(_cost(m) for m in picked),
            sum(1 for m in picked if _to_int(m.get("tier")) == 1),
            sum(1 for m in picked if _to_int(m.get("tier")) == 2),
            sum(1 for m in picked if _to_int(m.get("tier")) == 3),
            sum(1 for m in picked if _to_int(m.get("tier")) == 4))
        return picked

    # ==================================================================
    # 调试辅助
    # ==================================================================
    def audit_isolation(self, character: Any) -> Dict[str, Any]:
        """自查：该角色的上下文里有没有混进别人的东西。"""
        cid = self.char_mgr.resolve_id(character)
        if cid is None:
            return {"error": "角色不存在"}
        text = self.build(cid)
        foreign: List[str] = []
        for other in self.char_mgr.all():
            if int(other["character_id"]) == int(cid):
                continue
            other_mems = self.mem_mgr.list_for(other["character_id"], limit=50)
            for m in other_mems:
                content = str(m.get("content") or "")
                if content and content in text:
                    foreign.append("memory:%s" % m["memory_id"])
        forbidden = [mk for mk in FORBIDDEN_CONTEXT_MARKERS if mk in text]
        return {
            "char_id": cid,
            "chars": len(text),
            "forbidden_markers": forbidden,
            "foreign_memories": foreign[:10],
            "foreign_count": len(foreign),
        }


# ==============================================================================
# [追加点] 批 5 从此处继续：MemoryEngine / WebServer / CLI / main / 使用文档
# ==============================================================================



# ==============================================================================
# 24. MemoryEngine —— 门面：组合全部 manager
# ==============================================================================


def _pick_visibility_id(
    vis_index: Dict[int, List[Tuple[Optional[int], int]]],
    event_index: Optional[int],
    character_id: Optional[int],
) -> Optional[int]:
    """从 ``vis_index``（``character_id -> [(event_index, vis_id), ...]``）挑可见性 id。

    * 记忆带了 ``source_event_index`` 时**必须精确匹配**该事件的可见性，
      否则宁可返回 ``None`` —— 绝不把 A 事件的认知挂到 B 事件的记忆上
      （SPEC Python 层强制校验 4：防串记忆）
    * 记忆没有 ``source_event_index`` 时，只有该角色本次**唯一**一条可见性
      才采用；多于一条就放弃，宁可少挂也不挂错
    """
    if character_id is None:
        return None
    entries = vis_index.get(int(character_id)) or []
    if not entries:
        return None
    if event_index is not None:
        for e_idx, vis_id in entries:
            if e_idx == event_index:
                return vis_id
        return None
    if len(entries) == 1:
        return entries[0][1]
    return None


# ══════════════════════════════════════════════════════════════════════
# 【17】总装引擎
# ══════════════════════════════════════════════════════════════════════

class MemoryEngine:
    """多角色长期记忆引擎的**门面**（SPEC「代码结构」第 17 项）。

    组合的 15 个子系统（属性名即 SPEC 中的简称）：

    ==================  ==========================  ============================
    属性                 类                          职责
    ==================  ==========================  ============================
    ``char_mgr``        ``CharacterManager``        角色注册 / 自动识别 / 活跃
    ``mem_mgr``         ``MemoryManager``           记忆读写 / 衰减 / 压缩 / 冲突
    ``event_mgr``       ``EventManager``            客观事件 + 事件链
    ``know_mgr``        ``KnowledgeManager``        非事件型事实
    ``belief_mgr``      ``BeliefManager``           信念（kind 分类）
    ``rel_mgr``         ``RelationshipManager``     单向关系 + 历史
    ``state_mgr``       ``StateManager``            角色自身状态 + 历史
    ``commit_mgr``      ``CommitmentManager``       承诺
    ``secret_mgr``      ``SecretManager``           秘密
    ``assoc_mgr``       ``AssociationManager``      记忆关联
    ``vis_mgr``         ``VisibilityManager``       事件可见性（单调性校验）
    ``llm``             ``LLMClient``               OpenAI 兼容客户端
    ``extractor``       ``MemoryExtractor``         规则 + LLM 抽取
    ``importer``        ``TavoImporter``            JSONL 导入（幂等 + 增量）
    ``context_builder`` ``ContextBuilder``          角色上下文 + Stance
    ==================  ==========================  ============================

    **写入铁律**：LLM 只产出提案，一切落库都经过 manager 的 Python 层校验。
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        config: Optional[Config] = None,
        config_path: Optional[Union[str, Path]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """按 ``config`` / ``config_path`` 组装全部子系统并建表。"""
        self.config: Config = config if config is not None else load_config(config_path)
        if db_path is not None:
            self.config.db_path = str(db_path)

        self.logger = logger or setup_logging(
            debug=bool(self.config.debug),
            log_dir=self.config.log_dir,
            log_file=self.config.log_file,
        )

        self.db = Database(self.config.db_path, config=self.config,
                           logger=self.logger)
        self.db.init_schema()

        # ---- 12 个 manager ----
        # event_mgr 与 vis_mgr 互相引用：先建 event_mgr（vis_mgr=None），
        # 再建 vis_mgr，最后回填 event_mgr.vis_mgr，避免构造期循环依赖。
        self.char_mgr = CharacterManager(self.db, self.config, self.logger)

        # ---- V3 追加：卡片层管理器（characters 的分组容器）----
        self.card_mgr = CardManager(self.db, config=self.config,
                                    char_mgr=self.char_mgr,
                                    logger=self.logger)

        self.event_mgr = EventManager(self.db, config=self.config,
                                      vis_mgr=None, logger=self.logger)
        self.vis_mgr = VisibilityManager(
            self.db, config=self.config, char_mgr=self.char_mgr,
            event_mgr=self.event_mgr, logger=self.logger)
        self.event_mgr.vis_mgr = self.vis_mgr

        self.llm = LLMClient(self.config, logger=self.logger)

        self.mem_mgr = MemoryManager(
            self.db, char_mgr=self.char_mgr, config=self.config,
            vis_mgr=self.vis_mgr, event_mgr=self.event_mgr,
            llm=self.llm, logger=self.logger)

        self.know_mgr = KnowledgeManager(self.db, self.char_mgr,
                                         self.config, self.logger)
        self.belief_mgr = BeliefManager(self.db, self.char_mgr,
                                        self.config, self.logger)
        self.assoc_mgr = AssociationManager(self.db, self.config,
                                            self.mem_mgr, self.logger)
        self.rel_mgr = RelationshipManager(self.db, self.char_mgr,
                                           self.config, self.logger,
                                           llm=self.llm)
        self.state_mgr = StateManager(self.db, self.char_mgr,
                                      self.config, self.logger)
        self.commit_mgr = CommitmentManager(self.db, self.char_mgr,
                                            self.config, self.logger)
        self.secret_mgr = SecretManager(self.db, self.char_mgr,
                                        self.config, self.logger)

        # ---- 3 个上层组件 ----
        self.extractor = MemoryExtractor(
            self.db, char_mgr=self.char_mgr, llm=self.llm,
            config=self.config, logger=self.logger)
        self.importer = TavoImporter(
            self.db, char_mgr=self.char_mgr, config=self.config,
            logger=self.logger)
        self.context_builder = ContextBuilder(
            self.char_mgr, self.mem_mgr, self.rel_mgr, self.state_mgr,
            self.know_mgr, self.commit_mgr, self.secret_mgr,
            self.belief_mgr, self.vis_mgr,
            config=self.config, llm=self.llm, logger=self.logger)

        # ---- [V2.2 铁律] 启动自愈：把历史遗留的散装角色归位到卡下 ----
        # 幂等且零写入（没有散装角色时只跑一条 SELECT）；这样即便老库、
        # 手工 SQL 或未覆盖的代码路径产生了无卡角色，下一次进程启动就会修好。
        try:
            adopted = self.card_mgr.adopt_orphan_characters()
            if adopted:
                self.logger.warning("[卡片] 启动自愈：%d 个散装角色已归位到「%s」",
                                    len(adopted), DEFAULT_CARD_NAME)
        except Exception as ex:
            self.logger.warning("[卡片] 启动自愈失败（不影响运行）：%s", ex)

        #: [V2.6 动态用户识别] 本轮请求从开场白/系统提示解析出的玩家名单
        #: （非空时**覆盖** config.user_names；每次识别开头重算）
        self._request_user_names: List[str] = []

        #: 本次进程内的累计统计（供 CLI / Web 展示，不落库）
        self.runtime_stats: Dict[str, int] = {
            "imported_messages": 0, "processed_messages": 0,
            "extractions": 0, "applied_events": 0, "applied_visibility": 0,
            "applied_memories": 0, "applied_beliefs": 0,
        }

        # ---- 批 9：中继自动角色识别用的角色名缓存（带 TTL）----
        #: characters 表全部角色名（内容扫描 3b 用，避免每个请求都查库）
        self._char_names_cache: List[str] = []
        #: 上面这份缓存的写入时刻（``time.time()``）
        self._char_names_at: float = 0.0
        self._char_names_lock = threading.Lock()
        #: 最近一次 ``_detect_character_from_request()`` 的命中来源
        self.last_char_source: str = "none"

        # ---- V3 追加：卡名缓存（带 TTL）+ 最近一次识别结果 ----
        #: cards 表全部卡名（中继扫 system prompt 认卡用）
        self._card_names_cache: List[str] = []
        #: 上面这份缓存的写入时刻（``time.time()``）
        self._card_names_at: float = 0.0
        self._card_names_lock = threading.Lock()
        #: 最近一次 ``_detect_card_and_speaker()`` 的完整结果
        self.last_card_detect: Dict[str, Any] = {
            "card": None, "speaker": None, "characters": [],
            "source": DETECT_SOURCE_NONE,
        }
        #: V3：本次请求/回写的卡名。判"这个名字该不该作为角色"时要用它
        #: （**名字 == 卡名 → 不是角色**，比如「某卡」只是卡名）
        self._current_card: str = ""
        #: V5.6：本轮这张卡有没有开【时间感知】（每轮识别时重置，默认关）
        self._current_time_aware: bool = False
        #: V5.8：本轮这张卡的【演员】名单（每轮重置；空 = 开场白没写）
        self._current_card_actors: List[str] = []
        #: [V6 阶段A] 异步回写的串行锁（保证暂存处理顺序稳定）
        self._ingest_serial_lock = threading.Lock()

        self.logger.info(
            "[引擎] 启动完成 db=%s llm=%s", self.config.db_path,
            "on" if self.llm.enabled else "off")

    # ==================================================================
    # 生命周期
    # ==================================================================
    def close(self) -> None:
        """关闭数据库连接。"""
        self.db.close()

    def __enter__(self) -> "MemoryEngine":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ==================================================================
    # [V6 阶段A] 边聊边记：**异步**回写（绝不阻塞用户看到回复的时间）
    # ==================================================================
    def ingest_turn_async(
        self,
        character_name: str,
        user_message: str,
        assistant_message: str,
        source: str = "relay",
        card: Optional[str] = None,
        extra_messages: Optional[Sequence[Any]] = None,
        messages: Optional[Sequence[Any]] = None,
    ) -> Optional[threading.Thread]:
        """把一轮对话丢进后台 daemon 线程回写（[V6 阶段A]）。

        * 主流程（转发 / 返回响应）**立即返回**，不等抽取、不等 LLM。
        * 所有后台回写共用 ``self._ingest_serial_lock`` **串行化**：
          保证「先到的请求先处理暂存」，不会因为并发把两轮的暂存搅在一起
          （``ingest_turn_staged`` 的 reroll 判定依赖 conversation_meta
          里那唯一一份 pending）。
        * ``llm.ingest_async=false`` -> 退回同步执行（排障开关）。
        * 返回后台线程对象（同步模式下返回 None）。**绝不抛异常。**
        """
        def _run() -> None:
            try:
                with self._ingest_serial_lock:
                    self.ingest_turn_staged(
                        character_name, user_message, assistant_message,
                        source=source, card=card,
                        extra_messages=extra_messages, messages=messages)
            except Exception as ex:      # 兜底：异步回写失败绝不冒泡
                self.logger.exception("[中继] 异步回写失败（已忽略）：%s", ex)

        if not bool(getattr(self.config.llm, "ingest_async", True)):
            self.logger.debug("[中继] ingest_async=false，改为同步回写")
            _run()
            return None
        try:
            th = threading.Thread(target=_run, name=RELAY_INGEST_THREAD,
                                  daemon=True)
            th.start()
            return th
        except Exception as ex:
            self.logger.warning("[中继] 后台回写线程启动失败（已忽略）：%s", ex)
            return None

    def describe(self) -> Dict[str, Any]:
        """引擎自检摘要（配置 + LLM 状态 + 各表条数）。"""
        out: Dict[str, Any] = {
            "app": APP_NAME, "version": APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "config": self.config.describe(),
            "llm": self.llm.describe(),
            "runtime_stats": dict(self.runtime_stats),
        }
        try:
            out["stats"] = self.summary_stats()
        except Exception as ex:
            out["stats_error"] = "%s: %s" % (type(ex).__name__, ex)
        return out

    # ==================================================================
    # 内部工具
    # ==================================================================
    def _current_card_id(self) -> Optional[int]:
        """本次请求的卡 id —— 建档裁决用它判断「是不是本卡已有的角色」。

        【为什么单独写】原先直接 ``getattr(self, "_current_card_id", None)``，
        而那个属性**在引擎里根本不存在** → 永远返回 None → ``card_id`` 参数
        形同虚设（改了等于没改）。这里用真实的 ``card_mgr.get()`` 取名取 id。

        取不到就返回 None：``resolve_or_reject`` 会退化成全局名字/别名匹配，
        **绝不因为拿不到卡 id 就放行新建**。
        """
        name = str(getattr(self, "_current_card", "") or "").strip()
        if not name:
            return None
        try:
            row = self.card_mgr.get(name)
        except Exception as ex:
            self.logger.debug("[建档] 取卡 %r 失败：%s", name, ex)
            return None
        if isinstance(row, dict):
            return _to_int(row.get("card_id"))
        return _to_int(row)

    def _ensure_character(self, name: Any, ctx=None,
                          caller: str = "") -> Optional[int]:
        """把名字（或 id / 别名）解析成 ``character_id``。

        解析不到时**自动注册**该角色并告警 —— 这样"新增第 5 个角色"
        永远不需要改代码（SPEC 最终检查清单）。
        """
        cid = self.char_mgr.resolve_id(name)
        if cid is not None:
            return cid
        clean = _bounded_str(name, NAME_MAX_LEN)
        if not clean:
            self.logger.warning("[引擎] 无法解析角色名 %r，跳过", name)
            return None
        # [V2.4 兜底防呆] 纯称呼（爸爸/哥哥/女儿…）且解析不到任何真名/别名时，
        # 拒绝建档 —— 否则又会造出一堆无意义空壳角色（历史教训：父亲/女儿/爸爸）。
        if self._refuse_bare_kinship(clean, "抽取建档"):
            return None
        # [用户幽灵修复 2026-09-19] 建档之前先判用户身份：命中则不建，
        # 直接返回 user 的 character_id（关系仍能正确指向用户）。
        # 老代码只挡亲属称呼，漏了用户真名（如「明」），于是抽取侧
        # _ensure_character("明") 建出 card_id=NULL 的幽灵角色。
        if self._is_user_name(clean):
            ur = None
            try:
                ur = self.char_mgr.get_user()
            except Exception:
                ur = None
            uid = _to_int((ur or {}).get("character_id"))
            self.logger.warning(
                "[引擎] 抽取建档：%r 命中「用户」身份，跳过建档（返回 uid=%s）",
                clean, uid)
            return uid
        # ★★ 唯一建档入口（2026-09-21）★★
        # 走到这一行，说明上面所有「查得到就返回」的路都走完了 —— 也就是
        # 接下来原本要 get_or_create 新建一个角色。新建资格现在只由
        # resolve_or_reject 裁决：LLM 输出给的名字必须落在「本轮真实说话人」
        # 或「客户端显式声明」里才放行，否则整条丢弃。
        _new_cid = self.char_mgr.resolve_or_reject(
            clean, self._current_card_id(), ctx, caller)
        if _new_cid is None:
            return None
        row = self.char_mgr.get(_new_cid)
        if row is None:
            self.logger.warning("[引擎] 自动注册角色失败：%r", clean)
            return None
        real_name = str(row.get("name") or clean)
        # ---- [V2.2 铁律] 角色必须有 card_id，严禁散装角色 ----
        # 优先挂本次请求的卡（``_current_card``）；请求没带卡名时挂兜底卡
        # ``DEFAULT_CARD_NAME``。**用户身份不挂卡**（它不参与记忆、也不是"角色"）。
        # 只影响**新建**路径，老角色的 card_id 一律不动。
        cid = int(row["character_id"])
        if self._is_user_name(real_name):
            self.logger.info("[角色] 新建 %s（id=%s, role_type=%s, card_id=None："
                             "用户身份不挂卡）", real_name, cid,
                             row.get("role_type"))
            return cid
        card_id: Optional[int] = None
        target_card = str(self._current_card or "").strip() or DEFAULT_CARD_NAME
        try:
            card_id = self.card_mgr.get_or_create(target_card)
            if card_id is not None:
                self.card_mgr.attach_character(card_id, real_name)
        except Exception as ex:
            self.logger.warning("[角色] 新建 %r 挂卡 %r 失败：%s",
                                real_name, target_card, ex)
            card_id = None
        self.logger.info("[角色] 新建 %s（id=%s, role_type=%s, card_id=%s）",
                         real_name, cid, row.get("role_type"),
                         card_id if card_id is not None else None)
        # 安全网：任何**其它路径**（中继扫描、导入）漏建的无卡角色，趁这次
        # 新建一并归位 —— 只在新角色出现时才多跑一次扫描，平时零开销。
        try:
            self.card_mgr.adopt_orphan_characters(target_card)
        except Exception as ex:
            self.logger.warning("[角色] 兜底归位扫描失败：%s", ex)
        return cid

    def _event_id_at(
        self,
        event_ids: Sequence[Optional[int]],
        index: Any,
        fallback_first: bool = False,
    ) -> Optional[int]:
        """按 ``source_event_index`` 取本次新建的 event_id。"""
        idx = _to_int(index)
        if idx is not None and 0 <= idx < len(event_ids):
            return event_ids[idx]
        if idx is None and fallback_first:
            for eid in event_ids:
                if eid:
                    return eid
        return None

    @staticmethod
    def _bump(stats: Dict[str, Any], key: str, n: int = 1) -> None:
        stats[key] = int(stats.get(key, 0)) + int(n)

    @staticmethod
    def _skip(stats: Dict[str, Any], reason: str) -> None:
        logging.getLogger(APP_NAME).info("[跳过] %s", reason)
        if len(stats["skipped"]) < 200:
            stats["skipped"].append(reason)

    # ==================================================================
    # 导入
    # ==================================================================
    def import_jsonl(
        self,
        path: Union[str, Path],
        mode: Optional[str] = None,
        process: bool = True,
        limit: Optional[int] = None,
        auto_register: bool = True,
    ) -> Dict[str, Any]:
        """导入聊天记录 JSONL，并（可选）立刻抽取未处理的增量消息。"""
        report: Dict[str, Any] = {"path": str(path), "mode": mode or DEFAULT_MODE}
        try:
            st = self.importer.import_file(path, auto_register=auto_register)
        except Exception as ex:
            self.logger.exception("[引擎] 导入异常：%s", ex)
            report["error"] = "%s: %s" % (type(ex).__name__, ex)
            return report
        report["import"] = st
        self.runtime_stats["imported_messages"] += int(st.get("imported") or 0)
        try:
            synced = self._sync_user_flags()
            if synced:
                report["user_flagged"] = synced
        except Exception as ex:
            self.logger.warning("[引擎] 同步 is_user 标记失败：%s", ex)

        if process and int(st.get("imported") or 0) > 0:
            report["extraction"] = self.process_pending(mode=mode, limit=limit)
        else:
            report["extraction"] = {
                "processed": 0, "batches": 0,
                "reason": "没有新增消息或 process=False",
            }
        return report

    # ==================================================================
    # 抽取 + 落库
    # ==================================================================
    def process_pending(
        self,
        mode: Optional[str] = None,
        limit: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """对 ``processed = 0`` 的消息做增量抽取并落库。

        每批 ``extraction_interval``（默认 10）条消息走一次
        ``MemoryExtractor.extract_from_messages``，然后 ``_apply_extraction``。
        处理完立即 ``mark_processed``，因此**重复运行不会重复抽取**。
        """
        md = str(mode or DEFAULT_MODE).strip().lower()
        if md not in VALID_MODES:
            self.logger.warning("[引擎] 未知 mode=%r，回落 %s", mode, DEFAULT_MODE)
            md = DEFAULT_MODE

        batch = max(1, int(batch_size or
                           self.config.memory.extraction_interval or 10))
        remaining = _to_int(limit)

        agg: Dict[str, Any] = {
            "mode": md, "processed": 0, "batches": 0, "empty": 0,
            "errors": 0, "events": 0, "visibility": 0, "memories": 0,
            "beliefs": 0, "knowledge": 0, "commitments": 0, "secrets": 0,
            "relationship_changes": 0, "state_changes": 0,
            "applied": 0, "skipped": [],
        }

        while True:
            take = batch
            if remaining is not None:
                if remaining <= 0:
                    break
                take = min(batch, remaining)

            try:
                msgs = self.importer.pending_messages(limit=take)
            except Exception as ex:
                self.logger.exception("[引擎] 取待处理消息失败：%s", ex)
                agg["errors"] += 1
                break
            if not msgs:
                break

            try:
                result = self.extractor.extract_from_messages(
                    msgs, mode=md, roster=self._extraction_roster_text())
            except Exception as ex:
                self.logger.exception("[引擎] 抽取异常，本批跳过：%s", ex)
                agg["errors"] += 1
                result = None

            if result is None or result.is_empty():
                agg["empty"] += 1

            if result is not None:
                try:
                    applied = self._apply_extraction(result, msgs)
                    agg["applied"] += int(applied.get("total") or 0)
                    for key in ("events", "visibility", "memories", "beliefs",
                                "knowledge", "commitments", "secrets",
                                "relationship_changes", "state_changes"):
                        agg[key] += int(applied.get(key) or 0)
                    agg["skipped"].extend(applied.get("skipped") or [])
                    self.runtime_stats["extractions"] += 1
                    self.runtime_stats["applied_events"] += int(
                        applied.get("events") or 0)
                    self.runtime_stats["applied_visibility"] += int(
                        applied.get("visibility") or 0)
                    self.runtime_stats["applied_memories"] += int(
                        applied.get("memories") or 0)
                    self.runtime_stats["applied_beliefs"] += int(
                        applied.get("beliefs") or 0)
                except Exception as ex:
                    self.logger.exception("[引擎] 落库异常，本批跳过：%s", ex)
                    agg["errors"] += 1

            ids = [m.get("message_id") for m in msgs]
            try:
                self.importer.mark_processed([i for i in ids if i])
            except Exception as ex:
                self.logger.exception("[引擎] 标记已处理失败：%s", ex)
                agg["errors"] += 1

            agg["processed"] += len(msgs)
            agg["batches"] += 1
            self.runtime_stats["processed_messages"] += len(msgs)
            if remaining is not None:
                remaining -= len(msgs)

        agg["skipped"] = agg["skipped"][:200]
        self.logger.info(
            "[引擎] 增量抽取完成：模式=%s 消息=%d 批=%d 事件=%d 可见性=%d "
            "记忆=%d 信念=%d", md, agg["processed"], agg["batches"],
            agg["events"], agg["visibility"], agg["memories"], agg["beliefs"])
        return agg

    #: [去重] 同角色最近多少秒内视为「同一批」记忆
    MEM_DUP_WINDOW_SEC = 300
    #: [去重] content 相似度阈值（>= 则跳过不写）
    MEM_DUP_SIM = 0.85

    def _is_recent_duplicate(
        self, cid: Any, content: Any,
    ) -> Optional[Tuple[int, float]]:
        """[去重] 同角色最近 ``MEM_DUP_WINDOW_SEC`` 秒内是否已有高度相似记忆。

        返回 ``(memory_id, similarity)``；没命中返回 None。用于
        ``_apply_extraction`` 写库前的最后一道闸 —— LLM 常在同一段对话里把
        同一件事拆成多条近似记忆，逐条入库会让检索被同义句灌满。
        """
        text = str(content or "").strip()
        ccid = _to_int(cid)
        if not text or not ccid:
            return None
        try:
            rows = self.db.query(
                "SELECT memory_id, content, created_at FROM memories "
                "WHERE owner_character_id = ? "
                "ORDER BY memory_id DESC LIMIT 50", (ccid,))
        except Exception:
            return None
        cutoff = time.time() - float(self.MEM_DUP_WINDOW_SEC)
        for r in rows:
            dt = _parse_iso(r.get("created_at"))
            if dt is None:
                continue
            try:
                if dt.timestamp() < cutoff:
                    continue
            except Exception:
                continue
            try:
                sim = float(_similarity(text, r.get("content")))
            except Exception:
                continue
            if sim >= float(self.MEM_DUP_SIM):
                return (int(r.get("memory_id")), sim)
        return None

    def _apply_extraction(
        self,
        result: ExtractionResult,
        window_msgs: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        """把 ``ExtractionResult`` 按**严格顺序**落库。

        顺序（不可调换，后面的步骤要引用前面的 id）：

        1. ``events``               -> ``event_id``
        2. ``visibility_updates``   -> 引用 ``event_id``，得到 ``vis_id``
        3. ``memories``             -> 引用 ``event_id`` + ``vis_id``
        4. ``beliefs``              -> 引用 ``event_id``
        5. ``knowledge`` / ``commitments`` / ``secrets``
        6. ``relationship_changes`` / ``state_changes``

        每一步独立 ``try/except`` + ``logging``：任何一步炸了都只丢那一步，
        绝不中断其余步骤。
        """
        stats: Dict[str, Any] = {
            "events": 0, "visibility": 0, "memories": 0, "beliefs": 0,
            "knowledge": 0, "commitments": 0, "secrets": 0,
            "relationship_changes": 0, "state_changes": 0,
            "total": 0, "skipped": [], "errors": 0,
            "owner_intercepted": 0, "creation_rejected": 0,
            "reinforced": 0,
        }

        # [时间层] 读本卡剧情时间，供 add_memory 传参
        _st_for_mem = ""
        try:
            _card_now = str(getattr(self, "_current_card", "") or "")
            if _card_now:
                _st_for_mem = str(
                    self.db.get_meta("story_time:" + _card_now) or "")
        except Exception:
            _st_for_mem = ""

        if result is None:
            return stats

        # ---------------- [owner 守卫] 本次注入窗口的说话人 ----------------
        # 【为什么】客户端会把 system 提示词拼进 user 消息正文（实测 Tavo 的状态栏
        # 规范里列了全角色名单 + 样例心声）。LLM 从正文里读到那些人名，就会把
        # owner_name 写成「只被提及、并没有说话」的角色 —— 实测用户自己的第一人称
        # 经历被判给了丁。这里只承认「窗口里真的说过话的人」。
        #
        # 拿不到窗口（window_msgs 为空）→ 不拦截，保持原行为。
        _speaker_names: set = set()
        _name_by_msg: Dict[str, str] = {}
        _main_speaker: Optional[str] = None
        _hits: Dict[str, int] = {}
        try:
            for _m in (window_msgs or []):
                if not isinstance(_m, dict):
                    continue
                _nm = str(_m.get("name") or "").strip()
                _mid = str(_m.get("message_id") or "").strip()
                if not _nm:
                    continue
                _speaker_names.add(_nm)
                if _mid:
                    _name_by_msg[_mid] = _nm
                if not _m.get("is_user"):
                    _hits[_nm] = _hits.get(_nm, 0) + 1
            if _hits:
                _main_speaker = sorted(_hits.items(),
                                       key=lambda kv: (-kv[1], kv[0]))[0][0]
        except Exception as ex:
            self.logger.warning("[抽取] owner 守卫初始化失败（本次不拦截）：%s", ex)
            _speaker_names = set()
        # 用户真名也算「说话人」——他们本来就该被 _should_skip_character 挡掉，
        # 不该在这里被改写成别的角色。
        # ⚠️ _user_names() 是 MemoryManager 的方法，MemoryEngine 上没有；
        #    必须从 config 读。否则 AttributeError 会被吞掉，整个守卫静默失效。
        try:
            _cfg_mem = getattr(self.config, "memory", None)
            _users = getattr(_cfg_mem, "user_names", ()) or ()
            if isinstance(_users, str):
                _users = (_users,)
            _users = list(_users) + list(
                getattr(self, "_request_user_names", []) or [])
            for _un in _users:
                _un = str(_un or "").strip()
                if _un:
                    _speaker_names.add(_un)
        except Exception as ex:
            self.logger.warning("[抽取] owner 守卫：读用户名单失败：%s", ex)

        # ---------------- [建档裁决上下文] ★唯一建档入口的证据 ----------------
        # 有了它，「新建角色」这件事才有来源可查：见 CreationContext 的说明。
        try:
            _ctx_card = str(getattr(self, "_current_card", "") or "").strip() \
                or None
        except Exception:
            _ctx_card = None
        try:
            _ctx_card_names = list(self._card_character_names(_ctx_card))
        except Exception as ex:
            self.logger.warning("[建档] 取本卡角色名单失败（按空处理）：%s", ex)
            _ctx_card_names = []
        try:
            _ctx_declared = list(getattr(self, "_current_card_actors", []) or [])
        except Exception:
            _ctx_declared = []
        try:
            _cfg_m = getattr(self.config, "memory", None)
            _ctx_unames = list(getattr(_cfg_m, "user_names", ()) or []) + \
                list(getattr(self, "_request_user_names", []) or [])
        except Exception:
            _ctx_unames = []
        creation_ctx = CreationContext(
            speakers=_speaker_names, declared=_ctx_declared,
            card_names=_ctx_card_names, user_names=_ctx_unames)
        self.logger.info(
            "[建档] 裁决上下文：说话人=%s 客户端声明=%s 本卡角色=%s 玩家名=%s",
            sorted(creation_ctx.speakers), sorted(creation_ctx.declared),
            sorted(creation_ctx.card_names), sorted(creation_ctx.user_names))

        #: event_ids[i] 对应 result.events[i]（None 表示该事件没建成功）
        event_ids: List[Optional[int]] = []
        #: character_id -> [(event_index, vis_id), ...]
        vis_index: Dict[int, List[Tuple[Optional[int], int]]] = {}

        # ---------------- 1) events ----------------
        try:
            for ev in (result.events or []):
                if not isinstance(ev, dict):
                    self._skip(stats, "事件不是 dict")
                    continue
                summary = str(ev.get("summary") or "").strip()
                if not summary:
                    self._skip(stats, "事件缺少 summary")
                    event_ids.append(None)
                    continue
                try:
                    eid = self.event_mgr.create_event(
                        summary=summary,
                        event_type=ev.get("event_type") or DEFAULT_EVENT_TYPE,
                        importance=_clamp(ev.get("importance"), 0.0, 1.0,
                                          DEFAULT_IMPORTANCE),
                        emotional_intensity=_clamp(
                            ev.get("emotional_intensity"), 0.0, 1.0,
                            DEFAULT_EMOTIONAL_INTENSITY),
                        occurred_at=ev.get("occurred_at"),
                        location=str(ev.get("location") or ""),
                        source_message_ids=ev.get("source_message_ids"),
                        is_factual=bool(ev.get("is_factual", 1)),
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][1 事件] 写入异常：%s", ex)
                    eid = None
                event_ids.append(eid)
                if eid is not None:
                    self._bump(stats, "events")
                else:
                    self._skip(stats, "事件写入被拒：%s" % summary[:40])
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][1 事件] 整体异常：%s", ex)

        # ---------------- 2) visibility ----------------
        try:
            for vu in (result.visibility_updates or []):
                if not isinstance(vu, dict):
                    self._skip(stats, "可见性不是 dict")
                    continue
                idx = _to_int(vu.get("event_index"))
                eid = self._event_id_at(event_ids, idx, fallback_first=True)
                if eid is None:
                    self._skip(stats, "可见性找不到对应事件（index=%r）" % idx)
                    continue
                _vnm = (vu.get("character") or vu.get("name")
                        or vu.get("owner_name"))
                # [幽灵角色修复] 事件参与者只允许引用「窗口里真出现过的说话人」
                # 或库里已有的角色。不认识的名字不再顺手建档 —— 否则 LLM 一旦编出
                # 虚构人物，就会生成一批 message_count=0 的幽灵角色挂在某个卡下面
                # （实测 card7 被塞进 11 个：角色G/角色J/角色H/角色K/角色I…）。
                if _vnm and _speaker_names:
                    _vn = str(_vnm).strip()
                    if _vn not in _speaker_names and not self.char_mgr.get(_vn):
                        self._skip(stats,
                                   "可见性角色不在已知范围（%r），不建档" % (_vn,))
                        continue
                cid = self._ensure_character(_vnm, creation_ctx,
                                             "visibility.character")
                if cid is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "可见性找不到角色")
                    continue
                try:
                    vis_id = self.vis_mgr.set_visibility(
                        event_id=eid,
                        character_id=cid,
                        state=vu.get("state"),
                        partial_content=vu.get("partial_content"),
                        source=vu.get("source"),
                        source_message_id=vu.get("source_message_id"),
                        confidence=_clamp(vu.get("confidence"), 0.0, 1.0,
                                          DEFAULT_VISIBILITY_CONFIDENCE),
                        present=bool(vu.get("present")),
                        role_in_event=vu.get("role_in_event"),
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][2 可见性] 写入异常：%s", ex)
                    vis_id = None
                if vis_id is not None:
                    self._bump(stats, "visibility")
                    vis_index.setdefault(int(cid), []).append((idx, int(vis_id)))
                else:
                    self._skip(stats, "可见性被策略拒绝（event=%s char=%s）"
                               % (eid, cid))
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][2 可见性] 整体异常：%s", ex)

        # ---------------- 3) memories ----------------
        try:
            for mem in (result.memories or []):
                if not isinstance(mem, dict):
                    self._skip(stats, "记忆不是 dict")
                    continue
                content = str(mem.get("content") or "").strip()
                if not content:
                    self._skip(stats, "记忆缺少 content")
                    continue
                # V3：卡名 / 用户名不建档、不写记忆
                # [出戏过滤] 戏外元话语不落库
                if _is_ooc_meta_text(mem.get("content")):
                    self._skip(stats, "记忆是戏外元话语：%s"
                               % (str(mem.get("content"))[:30],))
                    continue
                _oname = mem.get("owner_name") or mem.get("owner")
                # [owner 守卫] owner 必须是窗口里的说话人；只是被正文提到的
                # 角色 → 退回该条记忆引用那条消息的说话人（其次窗口主说话人）
                if _oname and _speaker_names:
                    _on = str(_oname).strip()
                    if _on and _on not in _speaker_names:
                        _roster = list(getattr(creation_ctx, "card_names", ()) or [])
                        if _on in _roster:
                            # 本卡角色，本轮只是没开口 → 保留原 owner，绝不改挂。
                            # （改挂会把 A 的记忆记到 B 头上，是"妈妈妹妹混在一起"的元凶）
                            self.logger.info(
                                "[抽取] owner 不在本轮说话人但属本卡：%s → 保留", _on)
                        elif not _roster:
                            # 拿不到本卡阵容（CLI 抽取 / 首轮角色还没登记）
                            # → 沿用旧的改挂行为，避免把 owner 全判成"不在本卡"
                            _fb = (_name_by_msg.get(
                                       str(mem.get("source_message_id") or "").strip())
                                   or _main_speaker)
                            if _fb:
                                stats["owner_intercepted"] += 1
                                self.logger.info(
                                    "[抽取] owner 越界拦截：%s → %s"
                                    "（%s 只在正文里被提及，不是说话人）",
                                    _on, _fb, _on)
                                _oname = _fb
                        else:
                            stats["owner_intercepted"] += 1
                            self.logger.info(
                                "[抽取] owner 不在本卡：%s → 丢弃", _on)
                            self._skip(stats, "记忆 owner %r 不在本卡角色清单"
                                       % (_on,))
                            continue
                if self._should_skip_character(_oname):
                    self._skip(stats, "记忆 owner %r 是卡名/用户（不建记忆）"
                               % (_oname,))
                    continue
                cid = self._ensure_character(_oname, creation_ctx,
                                             "memory.owner_name")
                if cid is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "记忆找不到 owner")
                    continue
                idx = _to_int(mem.get("source_event_index"))
                eid = self._event_id_at(event_ids, idx)
                vis_id = _pick_visibility_id(vis_index, idx, cid)
                # [C2 写入侧判重] LLM 判定"和【已有记忆】某条同一概念/事件/规矩"
                #   → 直接强化那条，不再新增一条（用词不同也算）
                _act = str(mem.get("action") or "add").strip().lower()
                if _act == "reinforce":
                    _rid = _to_int(mem.get("reinforce_id"))
                    if _rid is not None:
                        _old = self.db.query_one(
                            "SELECT owner_character_id FROM memories "
                            "WHERE memory_id = ?", (_rid,))
                        if _old and int(_old["owner_character_id"]) == int(cid):
                            try:
                                _ok = self.mem_mgr.reinforce(
                                    _rid, boost=MEM_REINFORCE_DEFAULT)
                            except Exception as ex:
                                _ok = False
                                self.logger.warning(
                                    "[记忆] reinforce 异常，落回 add：%s", ex)
                            if _ok:
                                self._bump(stats, "reinforced")
                                self.logger.info(
                                    "[记忆] reinforce #%s（owner=%s，来源：%s）",
                                    _rid, cid, content[:30])
                                continue        # 不再 add
                            self.logger.warning(
                                "[记忆] reinforce 返回 False，落回 add：#%s", _rid)
                        else:
                            self.logger.warning(
                                "[记忆] reinforce 拒绝：id=%s 不属于 owner=%s"
                                "（落回 add）", _rid, cid)
                    else:
                        self.logger.warning(
                            "[记忆] action=reinforce 但 reinforce_id 非法，"
                            "落回 add：%r", mem.get("reinforce_id"))

                # [去重] 同一角色近 5 分钟内已有相似度 >=0.85 的记忆 → 跳过
                try:
                    _dup = self._is_recent_duplicate(cid, content)
                except Exception:
                    _dup = None
                if _dup is not None:
                    self._skip(stats, "记忆与近 5 分钟内 #%s 重复"
                               "（相似度 %.2f），跳过：%s"
                               % (_dup[0], _dup[1], content[:30]))
                    continue
                try:
                    memory_id = self.mem_mgr.add_memory(
                        owner=cid,
                        source_type=str(mem.get("source_type")
                                        or MEM_SOURCE_UNKNOWN).strip().upper(),
                        content=content,
                        memory_type=mem.get("memory_type") or DEFAULT_MEMORY_TYPE,
                        importance=_clamp(mem.get("importance"), 0.0, 1.0,
                                          DEFAULT_IMPORTANCE),
                        confidence=_clamp(mem.get("confidence"), 0.0, 1.0,
                                          DEFAULT_CONFIDENCE),
                        emotional_intensity=_clamp(
                            mem.get("emotional_intensity"), 0.0, 1.0,
                            DEFAULT_EMOTIONAL_INTENSITY),
                        source_event_id=eid,
                        source_message_id=mem.get("source_message_id"),
                        source_visibility_id=vis_id,
                        is_subjective=bool(mem.get("is_subjective", 1)),
                        tags=mem.get("tags"),
                        # [V6 阶段B] 抽取入库时定级：身份/核心关系/不可逆 -> 1，
                        # 当前情绪/动作/场景 -> 4，其他 3
                        # [修复 2026-09-18] _classify_tier 是 MemoryManager 的
                        # staticmethod，MemoryEngine 上没有 → 必须走 self.mem_mgr，
                        # 否则每条记忆写入都抛 AttributeError（记忆恒为 0）
                        tier=self.mem_mgr._classify_tier(
                            content, mem.get("memory_type"),
                            mem.get("emotional_intensity")),
                        auto_create_event=True,
                        story_time=_st_for_mem,
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][3 记忆] 写入异常：%s", ex)
                    memory_id = None
                if memory_id is not None:
                    self._bump(stats, "memories")
                    try:
                        self.assoc_mgr.auto_link_by_tokens(
                            memory_id, content=content, owner_id=cid)
                    except Exception as ex:
                        self.logger.warning("[引擎][3 记忆] 自动关联失败：%s", ex)
                else:
                    self._skip(stats, "记忆写入被拒：%s" % content[:40])
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][3 记忆] 整体异常：%s", ex)

        # ---------------- 4) beliefs ----------------
        try:
            for bl in (result.beliefs or []):
                if not isinstance(bl, dict):
                    self._skip(stats, "信念不是 dict")
                    continue
                statement = str(bl.get("statement") or "").strip()
                if not statement:
                    self._skip(stats, "信念缺少 statement")
                    continue
                # [出戏过滤] 戏外元话语不落库
                if _is_ooc_meta_text(statement):
                    self._skip(stats, "信念是戏外元话语：%s" % (statement[:30],))
                    continue
                # V3：卡名 / 用户名不建档、不写信念
                _bname = bl.get("owner_name") or bl.get("owner")
                if self._should_skip_character(_bname):
                    self._skip(stats, "信念 owner %r 是卡名/用户（不写信念）"
                               % (_bname,))
                    continue
                cid = self._ensure_character(_bname, creation_ctx,
                                             "belief.owner_name")
                if cid is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "信念找不到 owner")
                    continue

                kind = str(bl.get("kind") or BELIEF_BELIEF).strip().upper()
                if kind == BELIEF_FACT:
                    # Python 层强制校验 2：FACT 只能由规则层产出
                    gen = GENERATED_BY_RULE
                else:
                    gen = str(bl.get("generated_by") or GENERATED_BY_LLM).lower()
                    if gen not in VALID_BELIEF_GENERATORS:
                        gen = GENERATED_BY_LLM
                subj_kind = str(bl.get("subject_kind") or BELIEF_SUBJECT_FACT)
                try:
                    belief_id = self.belief_mgr.add_belief(
                        owner=cid,
                        kind=kind,
                        subject_kind=subj_kind,
                        statement=statement,
                        subject_ref=bl.get("subject_ref"),
                        confidence=_clamp(bl.get("confidence"), 0.0, 1.0,
                                          DEFAULT_BELIEF_CONFIDENCE),
                        based_on_event_id=self._event_id_at(
                            event_ids, bl.get("based_on_event_index")),
                        generated_by=gen,
                        source=bl.get("source"),
                        tags=bl.get("tags"),
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][4 信念] 写入异常：%s", ex)
                    belief_id = None
                if belief_id is not None:
                    self._bump(stats, "beliefs")
                else:
                    self._skip(stats, "信念写入被拒：%s" % statement[:40])
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][4 信念] 整体异常：%s", ex)

        # ---------------- 5) knowledge / commitments / secrets ----------------
        stats = self._apply_knowledge_block(result, stats, event_ids, creation_ctx)
        stats = self._apply_commitments_block(result, stats, event_ids, creation_ctx)
        stats = self._apply_secrets_block(result, stats, event_ids, creation_ctx)

        # ---------------- 6) relationships / states ----------------
        stats = self._apply_relationship_block(result, stats, event_ids, creation_ctx)
        stats = self._apply_state_block(result, stats, creation_ctx)

        stats["total"] = sum(int(stats.get(k) or 0) for k in (
            "events", "visibility", "memories", "beliefs", "knowledge",
            "commitments", "secrets", "relationship_changes", "state_changes"))
        self.logger.info(
            "[引擎] 落库完成：事件=%d 可见性=%d 记忆=%d 强化=%d 信念=%d 知识=%d "
            "承诺=%d 秘密=%d 关系=%d 状态=%d 拒绝=%d 异常=%d 建档拒绝=%d",
            stats["events"], stats["visibility"], stats["memories"],
            stats.get("reinforced", 0),
            stats["beliefs"], stats["knowledge"], stats["commitments"],
            stats["secrets"], stats["relationship_changes"],
            stats["state_changes"], len(stats["skipped"]), stats["errors"],
            stats.get("creation_rejected", 0))
        return stats

    # ---- 第 5 步的三个子块（拆出来只为让 _apply_extraction 可读）----
    def _apply_knowledge_block(
        self,
        result: ExtractionResult,
        stats: Dict[str, Any],
        event_ids: Sequence[Optional[int]],
        ctx: "CreationContext" = None,
    ) -> Dict[str, Any]:
        """写入非事件型知识（``event_id`` 强制 NULL，见 SPEC 校验 9）。"""
        try:
            for ku in (result.knowledge_updates or []):
                if not isinstance(ku, dict):
                    self._skip(stats, "知识不是 dict")
                    continue
                subject = str(ku.get("subject") or "").strip()
                if not subject:
                    self._skip(stats, "知识缺少 subject")
                    continue
                # [出戏过滤] 戏外元话语不落库
                if _is_ooc_meta_text(subject):
                    self._skip(stats, "知识是戏外元话语：%s" % (subject[:30],))
                    continue
                # V3：卡名 / 用户名不建档、不写知识
                _kname = ku.get("owner_name") or ku.get("owner")
                if self._should_skip_character(_kname):
                    self._skip(stats, "知识 owner %r 是卡名/用户（不写知识）"
                               % (_kname,))
                    continue
                cid = self._ensure_character(_kname, ctx,
                                             "knowledge.owner_name")
                if cid is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "知识找不到 owner")
                    continue
                if ku.get("event_id") not in (None, ""):
                    self.logger.warning(
                        "[引擎][5 知识] 忽略提案里的 event_id=%r —— 事件型知识"
                        "必须走 event_visibility，非事件型 knowledge 的 event_id"
                        " 必须为 NULL", ku.get("event_id"))
                try:
                    kid = self.know_mgr.set_knowledge(
                        owner=cid,
                        subject=subject,
                        status=ku.get("status") or DEFAULT_KNOWLEDGE_STATUS,
                        event_id=None,
                        confidence=_clamp(ku.get("confidence"), 0.0, 1.0, 0.5),
                        source=ku.get("source"),
                        allow_event_link=False,
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][5 知识] 写入异常：%s", ex)
                    kid = None
                if kid is not None:
                    self._bump(stats, "knowledge")
                else:
                    self._skip(stats, "知识写入被拒：%s" % subject[:40])
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][5 知识] 整体异常：%s", ex)
        return stats

    def _apply_commitments_block(
        self,
        result: ExtractionResult,
        stats: Dict[str, Any],
        event_ids: Sequence[Optional[int]],
        ctx: "CreationContext" = None,
    ) -> Dict[str, Any]:
        """写入承诺。"""
        try:
            for cm in (result.commitments or []):
                if not isinstance(cm, dict):
                    self._skip(stats, "承诺不是 dict")
                    continue
                content = str(cm.get("content") or "").strip()
                if not content:
                    self._skip(stats, "承诺缺少 content")
                    continue
                promiser = self._ensure_character(
                    cm.get("promiser_name") or cm.get("promiser"),
                    ctx, "commitment.promiser")
                if promiser is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "承诺找不到承诺者")
                    continue
                promisee = None
                if cm.get("promisee_name") or cm.get("promisee"):
                    promisee = self._ensure_character(
                        cm.get("promisee_name") or cm.get("promisee"),
                        ctx, "commitment.promisee")
                try:
                    out = self.commit_mgr.add(
                        promiser=promiser,
                        promisee=promisee,
                        content=content,
                        deadline=cm.get("deadline"),
                        source_event_id=self._event_id_at(
                            event_ids, cm.get("source_event_index")),
                        notes=str(cm.get("notes") or ""),
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][5 承诺] 写入异常：%s", ex)
                    out = None
                if out is not None:
                    self._bump(stats, "commitments")
                else:
                    self._skip(stats, "承诺写入被拒：%s" % content[:40])
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][5 承诺] 整体异常：%s", ex)
        return stats

    def _apply_secrets_block(
        self,
        result: ExtractionResult,
        stats: Dict[str, Any],
        event_ids: Sequence[Optional[int]],
        ctx: "CreationContext" = None,
    ) -> Dict[str, Any]:
        """写入秘密。"""
        try:
            for sc in (result.secrets or []):
                if not isinstance(sc, dict):
                    self._skip(stats, "秘密不是 dict")
                    continue
                content = str(sc.get("content") or "").strip()
                if not content:
                    self._skip(stats, "秘密缺少 content")
                    continue
                # V3：卡名 / 用户名不建档、不写秘密
                _sname = sc.get("owner_name") or sc.get("owner")
                if self._should_skip_character(_sname):
                    self._skip(stats, "秘密 owner %r 是卡名/用户（不写秘密）"
                               % (_sname,))
                    continue
                owner = self._ensure_character(_sname, ctx,
                                               "secret.owner_name")
                if owner is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "秘密找不到 owner")
                    continue
                try:
                    out = self.secret_mgr.add(
                        owner=owner,
                        content=content,
                        subject=str(sc.get("subject") or ""),
                        source_event_id=self._event_id_at(
                            event_ids, sc.get("source_event_index")),
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][5 秘密] 写入异常：%s", ex)
                    out = None
                if out is not None:
                    self._bump(stats, "secrets")
                else:
                    self._skip(stats, "秘密写入被拒：%s" % content[:40])
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][5 秘密] 整体异常：%s", ex)
        return stats

    def _apply_relationship_block(
        self,
        result: ExtractionResult,
        stats: Dict[str, Any],
        event_ids: Sequence[Optional[int]],
        ctx: "CreationContext" = None,
    ) -> Dict[str, Any]:
        """写入关系变化（clamp 与 |delta|>0.5 拒绝由 RelationshipManager 负责）。"""
        try:
            for rc in (result.relationship_changes or []):
                if not isinstance(rc, dict):
                    self._skip(stats, "关系变化不是 dict")
                    continue
                from_c = self._ensure_character(
                    rc.get("from_name") or rc.get("from"),
                    ctx, "relationship.subject")
                to_c = self._ensure_character(
                    rc.get("to_name") or rc.get("to"),
                    ctx, "relationship.object")
                if from_c is None or to_c is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "关系变化找不到角色")
                    continue
                try:
                    delta = float(rc.get("delta"))
                except Exception:
                    self._skip(stats, "关系变化 delta 非数值")
                    continue
                # [relations-1] 三档事件映射 + delta 截断
                #   由 rc.based_on_event_index 指向的 event.importance 派生 tier，
                #   再把 |delta| 截到该档上限（保号）。取不到事件 -> 默认 major。
                _imp: Optional[float] = None
                _ev_idx = rc.get("based_on_event_index")
                try:
                    _ev_i = int(_ev_idx) if _ev_idx is not None else None
                except Exception:
                    _ev_i = None
                if _ev_i is not None:
                    _evs = list(result.events or [])
                    if 0 <= _ev_i < len(_evs):
                        _ev = _evs[_ev_i]
                        if isinstance(_ev, dict):
                            try:
                                _imp = float(_ev.get("importance"))
                            except Exception:
                                _imp = None
                if _imp is None or _imp != _imp:
                    _tier, _cap = "major", REL_DELTA_CAP_MAJOR
                elif _imp < REL_TIER_MAJOR_MIN:
                    _tier, _cap = "daily", REL_DELTA_CAP_DAILY
                elif _imp < REL_TIER_IRREVERSIBLE_MIN:
                    _tier, _cap = "major", REL_DELTA_CAP_MAJOR
                else:
                    _tier, _cap = "irreversible", REL_DELTA_CAP_IRREVERSIBLE
                _delta_raw = delta
                delta = max(-_cap, min(_cap, delta))
                self.logger.info(
                    "[关系] tier=%s imp=%.2f 原 delta=%+.3f → 截断后 %+.3f"
                    "（%s → %s %s）",
                    _tier, (_imp if _imp is not None else float("nan")),
                    _delta_raw, delta, from_c, to_c, rc.get("field"))

                # [relations-6] SLOW 维度上升打折（下跌原速，不打折）
                _fld6 = str(rc.get("field") or "").strip().lower()
                if _fld6 in REL_SLOW_DIMENSIONS and delta > 0:
                    _d6 = delta
                    delta = delta * REL_SLOW_UP_DISCOUNT
                    self.logger.info(
                        "[关系] SLOW 打折 %s %+.3f -> %+.3f（x%.1f）",
                        _fld6, _d6, delta, REL_SLOW_UP_DISCOUNT)

                try:
                    ok = self.rel_mgr.adjust(
                        from_c=from_c,
                        to_c=to_c,
                        field_name=str(rc.get("field") or ""),
                        delta=delta,
                        reason=str(rc.get("reason") or ""),
                        source_event_id=self._event_id_at(
                            event_ids, rc.get("based_on_event_index")),
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][6 关系] 写入异常：%s", ex)
                    ok = False
                if ok:
                    self._bump(stats, "relationship_changes")
                    # [relations-7a] 怨恨峰值 + 残留下限（在调用方做）
                    try:
                        self.rel_mgr.apply_hate_floor(from_c, to_c)
                    except Exception as ex:
                        self.logger.warning(
                            "[关系][hate] 峰值/下限处理失败（忽略）：%s", ex)
                    # [relations-9] 低置信度维度弱信号累积
                    try:
                        self.rel_mgr.note_weak_signal(from_c, to_c,
                                                      rc.get("field"), delta)
                    except Exception as ex:
                        self.logger.warning(
                            "[关系][弱信号] 处理失败（忽略）：%s", ex)
                else:
                    self._skip(stats, "关系变化被拒：%s->%s %s %+0.3f"
                               % (from_c, to_c, rc.get("field"), delta))
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][6 关系] 整体异常：%s", ex)
        return stats

    def _apply_state_block(
        self,
        result: ExtractionResult,
        stats: Dict[str, Any],
        ctx: "CreationContext" = None,
    ) -> Dict[str, Any]:
        """写入角色自身状态（``allow_compat=False``：不碰 trust / affection）。"""
        try:
            for stc in (result.state_changes or []):
                if not isinstance(stc, dict):
                    self._skip(stats, "状态变化不是 dict")
                    continue
                # V3：卡名 / 用户名不建档、不写状态
                _stname = stc.get("character_name") or stc.get("character")
                if self._should_skip_character(_stname):
                    self._skip(stats, "状态 owner %r 是卡名/用户（不写状态）"
                               % (_stname,))
                    continue
                cid = self._ensure_character(_stname, ctx,
                                             "state.owner_name")
                if cid is None:
                    stats["creation_rejected"] += 1
                    self._skip(stats, "状态变化找不到角色")
                    continue
                field_name = str(stc.get("field") or "").strip().lower()
                if not field_name:
                    self._skip(stats, "状态变化缺少 field")
                    continue
                try:
                    ok = self.state_mgr.set_field(
                        cid=cid,
                        field_name=field_name,
                        value=stc.get("value"),
                        reason=str(stc.get("reason") or ""),
                        allow_compat=False,
                    )
                except Exception as ex:
                    stats["errors"] += 1
                    self.logger.exception("[引擎][6 状态] 写入异常：%s", ex)
                    ok = False
                if ok:
                    self._bump(stats, "state_changes")
                else:
                    self._skip(stats, "状态变化被拒：%s=%r"
                               % (field_name, stc.get("value")))
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[引擎][6 状态] 整体异常：%s", ex)
        return stats

    # ==================================================================
    # 上下文
    # ==================================================================
    def build_context(
        self,
        character: Any,
        current_message: str = "",
        debug: bool = False,
        user_character: Any = None,
        time_aware: Optional[bool] = None,
        card: Any = None,
        present_names: Optional[List[str]] = None,
    ) -> str:
        """生成某个角色的完整上下文文本（Stance 实时推导，不落库）。

        **V5.6**：``time_aware`` 为 None 时用本轮识别出的 ``self._current_time_aware``
        （开场白带【时间感知】开的卡才注入时间信息）；为 True 时顺便刷新
        「这张卡上次聊天时间」标记，供下次算「距上次对话」。
        """
        aware = bool(self._current_time_aware) if time_aware is None \
            else bool(time_aware)
        now_text = ""
        prev_text: Optional[str] = None
        if aware:
            try:
                now_text, prev_text = self._time_aware_stamp(
                    card if card is not None else self._current_card)
            except Exception as ex:
                self.logger.warning("[中继] 取时间信息失败：%s", ex)
        # [场景层] 加载本卡场景状态，传给 build 注入
        _scene_state = None
        try:
            _card_ref = card if card is not None else self._current_card
            _loaded = self._load_scene_state(_card_ref)
            if _loaded.get("locations") or _loaded.get("actions"):
                _scene_state = _loaded
                self.logger.info(
                    "[场景] 注入 card=%s loc=%d act=%d",
                    _card_ref,
                    len(_loaded.get("locations") or {}),
                    len(_loaded.get("actions") or {}))
        except Exception as ex:
            self.logger.warning("[场景] build_context 加载失败：%s", ex)

        # [时间层] 加载剧情时间，传给 build 注入
        _story_time = ""
        try:
            _story_time = str(self.db.get_meta("story_time:" + str(card or self._current_card or "")) or "")
        except Exception as ex:
            self.logger.warning("[时间] build_context 加载失败：%s", ex)

        try:
            return self.context_builder.build(
                character, current_message=current_message, debug=debug,
                user_character=user_character,
                time_aware=aware, time_now=now_text, time_prev=prev_text,
                present_names=present_names,
                scene_state=_scene_state,
                story_time=_story_time)
        except Exception as ex:
            self.logger.exception("[引擎] 上下文生成失败：%s", ex)
            return "（上下文生成失败：%s: %s）" % (type(ex).__name__, ex)

    def audit_isolation(self, character: Any) -> Dict[str, Any]:
        """自查某角色的上下文有没有混入别人的记忆 / 违禁标记。"""
        try:
            return self.context_builder.audit_isolation(character)
        except Exception as ex:
            self.logger.exception("[引擎] 隔离自查失败：%s", ex)
            return {"error": "%s: %s" % (type(ex).__name__, ex)}

    # ==================================================================
    # 维护
    # ==================================================================
    def _sync_user_flags(self) -> int:
        """把"在聊天记录里以 user 身份发言"的角色标成 ``is_user = 1``。

        ``TavoImporter`` 自动注册角色时不带 ``is_user``（批 4 逻辑，不改动），
        这里按 ``messages.is_user`` 反推补齐，让 ``CharacterManager.get_user()``
        与 Web 控制台能认出"用户本人"。返回被更新的角色数。
        """
        try:
            rows = self.db.query(
                "SELECT DISTINCT character_id FROM messages "
                "WHERE is_user = 1 AND character_id IS NOT NULL")
        except Exception as ex:
            self.logger.warning("[引擎] 读取 user 发言失败：%s", ex)
            return 0
        changed = 0
        try:
            with self.db.transaction():
                for r in rows:
                    cid = _to_int(r.get("character_id"))
                    if cid is None:
                        continue
                    cur = self.db.execute(
                        "UPDATE characters SET is_user = 1 "
                        "WHERE character_id = ? AND is_user = 0", (cid,))
                    if cur is not None and (cur.rowcount or 0) > 0:
                        changed += 1
        except Exception as ex:
            self.logger.warning("[引擎] 同步 is_user 标记失败：%s", ex)
            return changed
        if changed:
            self.logger.info("[引擎] 已把 %d 个角色标记为 user", changed)
        return changed

    def set_role(self, name: Any, role_type: str) -> bool:
        """设置角色类型；``role_type='user'`` 时同步 ``characters.is_user = 1``。"""
        if self.char_mgr.get(name) is None:
            if self.char_mgr.get_or_create(name, role_type=role_type) is None:
                return False
        ok = bool(self.char_mgr.set_role(name, role_type))
        if ok and str(role_type or "").strip().lower() == ROLE_USER:
            cid = self.char_mgr.resolve_id(name)
            if cid is not None:
                try:
                    with self.db.transaction():
                        self.db.execute(
                            "UPDATE characters SET is_user = 1 "
                            "WHERE character_id = ?", (int(cid),))
                except Exception as ex:
                    self.logger.warning("[引擎] 标记 user 失败：%s", ex)
        return ok

    def resolve_active(
        self,
        window_messages: Optional[int] = None,
        window_hours: Optional[float] = None,
        promote_main: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """刷新活跃角色标记；按配置决定是否顺带提升核心角色候选。"""
        active: List[int] = []
        try:
            active = self.char_mgr.auto_detect_active(window_messages,
                                                      window_hours)
        except Exception as ex:
            self.logger.exception("[引擎] 活跃角色检测失败：%s", ex)

        promoted: List[int] = []
        want_promote = (self.config.memory.auto_detect_main
                        if promote_main is None else bool(promote_main))
        if want_promote:
            try:
                promoted = self.char_mgr.promote_main_candidates()
            except Exception as ex:
                self.logger.exception("[引擎] 核心角色提升失败：%s", ex)
        return {"active": active, "promoted": promoted}

    # ==================================================================
    # 中继：自动角色识别（批 9 追加）
    # ==================================================================
    def character_names_cached(
        self,
        ttl: Optional[float] = None,
    ) -> List[str]:
        """characters 表里的全部角色名（进程内缓存 + TTL，默认 5 秒）。

        内容扫描（3b）要拿每个角色名去比对每条消息，逐条查库太贵，所以这里
        做一次查询 + 缓存；TTL 到点后重新查一次，避免新导入的角色一直看不见。
        ``ttl`` 传 None 时用模块常量 ``CHAR_NAME_CACHE_TTL_SEC``。
        """
        try:
            ttl_sec = float(CHAR_NAME_CACHE_TTL_SEC if ttl is None else ttl)
        except Exception:
            ttl_sec = CHAR_NAME_CACHE_TTL_SEC
        now = time.time()
        try:
            with self._char_names_lock:
                if (self._char_names_at > 0.0
                        and (now - self._char_names_at) < ttl_sec):
                    return list(self._char_names_cache)
        except Exception:
            pass

        names: List[str] = []
        try:
            for row in (self.char_mgr.all() or []):
                nm = _relay_fix_text(row.get("name")).strip()
                if nm and nm not in names:
                    names.append(nm)
        except Exception as ex:
            self.logger.warning("[中继] 读取角色名列表失败：%s", ex)
            names = []

        try:
            with self._char_names_lock:
                self._char_names_cache = names
                self._char_names_at = now
        except Exception:
            pass
        return list(names)

    def card_names_cached(self, ttl: Optional[float] = None) -> List[str]:
        """``cards`` 表里的全部卡名（进程内缓存 + TTL，默认 5 秒）。

        V3 追加。中继每次请求都要拿卡名去扫 system prompt，缓存一份避免
        每个请求都查库；读失败时返回空列表（绝不抛）。
        """
        try:
            span = float(ttl) if ttl is not None else 5.0
        except Exception:
            span = 5.0
        now = time.time()
        try:
            with self._card_names_lock:
                if self._card_names_cache and (now - self._card_names_at) < span:
                    return list(self._card_names_cache)
        except Exception:
            pass

        names: List[str] = []
        try:
            names = list(self.card_mgr.all_names() or [])
        except Exception as ex:
            self.logger.warning("[中继] 读取卡名列表失败：%s", ex)
            names = []

        try:
            with self._card_names_lock:
                self._card_names_cache = names
                self._card_names_at = now
        except Exception:
            pass
        return list(names)

    def remember_card_name(self, name: Any) -> None:
        """把刚识别/新建的卡名塞进缓存，省得 TTL 内又查一次库。"""
        nm = _relay_fix_text(name).strip()
        if not nm:
            return
        try:
            with self._card_names_lock:
                if nm not in self._card_names_cache:
                    self._card_names_cache.insert(0, nm)
        except Exception:
            pass

    def remember_character_name(self, name: Any) -> None:
        """把刚自动注册的角色名塞进缓存，省得 TTL 内又查一次库。"""
        nm = _relay_fix_text(name).strip()
        if not nm:
            return
        try:
            with self._char_names_lock:
                if nm not in self._char_names_cache:
                    self._char_names_cache.append(nm)
        except Exception:
            pass

    def _detect_character_from_request(
        self,
        messages: Any,
        qs: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """从一次中继请求里自动识别当前角色（批 9 追加）。

        优先级（第一个命中就用），**每一步都单独 try/except，失败继续下一步**：

        1. ``?char=``（URL query；最高优先级，用户想手动覆盖时用）
        2. ``X-Character`` 请求头
        3. 从 ``messages`` 里识别：

           * 3a. 最后一条 ``role=assistant`` 且带 ``name`` 的消息的 name
           * 3b. **【新增】第一条 ``role=system`` 的 content（角色卡介绍）**，
             与 characters 表里所有角色名做"名字 in 文本"匹配，统计出现次数，
             取最多的那个；判定阈值与 content_scan 一致（最高分 <
             ``CONTENT_SCAN_MIN_SCORE`` 或与第二名并列 → 不猜）。
             Tavo 每张卡的介绍都会反复出现主角名，扫 system 比扫对话正文稳，
             因此**换卡不需要改任何配置、不需要给每张卡配 URL**
           * 3c. 扫描全部 messages 的 content / name，与 characters 表里所有
             角色名做"名字 in 文本"匹配（区分大小写、中英文都支持），统计
             出现次数，取最多的那个；最高分 < ``CONTENT_SCAN_MIN_SCORE``
             或与第二名并列 → 不猜，返回 None
           * 3d. 第一条 ``role=system`` 的 content 里抠 "你是X" / "扮演X" /
             "角色名：X" / "你的名字是X"（新卡第一次用时库里还没有角色名，
             靠这一步抠出来注册）

        命中时把来源写进 ``self.last_char_source``：
        ``query`` / ``header`` / ``assistant_name`` / ``system_scan`` /
        ``content_scan`` / ``system_prompt``；全都没命中写 ``none`` 并返回
        ``None``。

        **本方法不注册角色**，返回的名字可能还不在 characters 表里
        （注册由中继层 ``_relay_get_or_create()`` 负责）。
        """
        self.last_char_source = "none"

        # **V5.1**：用户 / 卡名绝不当说话人 —— 命中就返回 None，
        # 让调用方继续往下一级兜底（显式 ?char= 也一起过滤：引擎本来就不给
        # user 角色建记忆，显式指定也只会写出一堆没有意义的 messages）。
        def _keep(nm: Any) -> Optional[str]:
            if nm and self._should_skip_character(nm):
                self.logger.info(
                    "[中继] speaker=%r 命中用户/卡名过滤（来源=%s），跳过",
                    nm, self.last_char_source)
                return None
            return nm

        # ---- 1) URL query ?char= ----
        try:
            qchar = _relay_query_char(qs)
            qchar = _keep(qchar)
            if qchar:
                self.last_char_source = "query"
                return qchar
        except Exception as ex:
            self.logger.warning("[中继] 识别(query)失败：%s", ex)

        # ---- 2) HTTP header X-Character ----
        try:
            raw: Any = None
            if isinstance(headers, dict):
                for key, value in headers.items():
                    if str(key).strip().lower() == RELAY_CHAR_HEADER.lower():
                        raw = value
                        break
            hchar = _relay_fix_text(raw).strip() if raw is not None else ""
            hchar = _keep(hchar)
            if hchar:
                self.last_char_source = "header"
                return hchar
        except Exception as ex:
            self.logger.warning("[中继] 识别(header)失败：%s", ex)

        msgs = [m for m in (messages or []) if isinstance(m, dict)]

        # [V2.6] 动态玩家名单：见 _load_request_user_names()
        self._load_request_user_names(msgs)

        # ---- 3a) 最后一条带 name 的 assistant ----
        try:
            for m in reversed(msgs):
                if str(m.get("role", "")).strip().lower() != "assistant":
                    continue
                nm = _relay_fix_text(m.get("name")).strip()
                if nm:
                    self.last_char_source = "assistant_name"
                    nm = _keep(nm)
                    if nm:
                        return nm
        except Exception as ex:
            self.logger.warning("[中继] 识别(assistant_name)失败：%s", ex)

        # ---- 3b) 【新增】先扫第一条 system（角色卡介绍）里的已知角色名 ----
        #      Tavo 每次请求都会把角色卡的完整介绍塞进 system，主角名在其中
        #      反复出现，比对话正文稳定得多 —— 换卡不用改任何配置。
        #      库里还没有这个角色名时这一步自然不命中，交给第 3d 步抠出来。
        try:
            picked = _keep(self._scan_system_prompt_known_names(msgs))
            if picked:
                self.last_char_source = "system_scan"
                return picked
        except Exception as ex:
            self.logger.warning("[中继] 识别(system_scan)失败：%s", ex)

        # ---- 3c) content / name 全量扫描（原有 content_scan，逻辑不变）----
        try:
            picked = _keep(self._scan_messages_for_character(msgs))
            if picked:
                self.last_char_source = "content_scan"
                return picked
        except Exception as ex:
            self.logger.warning("[中继] 识别(content_scan)失败：%s", ex)

        # ---- 3d) 第一条 system 里的 "你是X" / "扮演X" / "角色名：X"（原有，逻辑不变）----
        try:
            picked = _keep(self._scan_system_prompt_for_character(msgs))
            if picked:
                self.last_char_source = "system_prompt"
                return picked
        except Exception as ex:
            self.logger.warning("[中继] 识别(system_prompt)失败：%s", ex)

        self.logger.debug("[中继] 自动识别无结果，交给 default_character / "
                          "resolve_active 兜底")
        return None

    def _scan_messages_for_character(
        self,
        messages: Sequence[Dict[str, Any]],
        card: Any = None,
    ) -> Optional[str]:
        """扫描 messages 正文，找出出现次数最多的角色名。

        **V5.9**：候选名单不再是无脑全库 —— 统一由
        ``_character_candidates_for_scan()`` 给（【演员】 > 当前卡 > 全库）。
        候选为空 → 返回 ``None``，不猜。

        匹配就是最简单的 ``名字 in 文本``（区分大小写），阈值 / 并列保护见
        ``_scan_messages_for_character_in()``。
        """
        cands = self._character_candidates_for_scan(card)
        if not cands:
            self.logger.info("[中继] 内容扫描：候选名单为空，不猜")
            return None
        return self._scan_messages_for_character_in(messages, cands)

    def _scan_messages_for_character_in(
        self,
        messages: Sequence[Dict[str, Any]],
        names: Sequence[Any],
    ) -> Optional[str]:
        """**V5.8**：只在**给定名字列表**里扫 messages 正文。

        打分 / 阈值（``CONTENT_SCAN_MIN_SCORE``）/ 并列保护与全库版一致，
        用户身份自动剔除（避免「明」这种名字靠出现次数压过真角色）。
        """
        cand = [str(n).strip() for n in (names or [])
                if str(n or "").strip() and not self._is_user_name(n)]
        if not cand:
            self.logger.info("[中继] 受限内容扫描：候选名单为空，不猜")
            return None

        counts: Dict[str, int] = {}
        for m in messages:
            blob = _relay_message_text(m)
            nm_field = _relay_fix_text(m.get("name"))
            if nm_field:
                blob = blob + "\n" + nm_field
            if not blob:
                continue
            for name in cand:
                hit = blob.count(name)
                if hit:
                    counts[name] = counts.get(name, 0) + hit
        if not counts:
            self.logger.debug("[中继] 受限内容扫描：候选 %s 一个都没出现", cand)
            return None

        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top_name, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        if top < CONTENT_SCAN_MIN_SCORE:
            self.logger.info("[中继] 受限内容扫描最高分 %d（< %d）太弱，不猜：%s",
                             top, CONTENT_SCAN_MIN_SCORE, ranked[:3])
            return None
        if top - second < 1:
            self.logger.info("[中继] 受限内容扫描并列，不猜：%s", ranked[:3])
            return None
        self.logger.debug("[中继] 受限内容扫描得分（候选 %s）：%s", cand, ranked[:3])
        return top_name

    def _scan_messages_for_card_character(
        self,
        messages: Sequence[Dict[str, Any]],
        card_ref: Any,
    ) -> Optional[str]:
        """**V5.7**：只在「当前卡下的角色」里扫 messages 正文（受限版 content_scan）。

        动机：``_scan_messages_for_character()`` 是**全库**扫名字 —— 别的卡的
        角色只要在这段正文里被提到（典型：上一轮被错认成它、AI 于是在回复里
        复述了它的名字），就会被选成本卡的说话人，越滚越错（串卡）。

        卡已经识别出来时，候选必须收窄到「这张卡下已登记的角色」：

        * 候选 = ``characters WHERE card_id = <当前卡>``，剔除用户身份
        * 打分 / 阈值 / 并列保护与全库版完全一致（见 ``_scan_messages_for_character_in``）
        * 卡下没有角色 → 返回 ``None``（留给 LLM 兜底，或干脆不注入）
        * ``card_ref`` 为空时**不**走这里（调用方回退全库扫描，保持原行为）
        """
        try:
            names = [n for n in self._card_character_names(card_ref)
                     if n and not self._is_user_name(n)]
        except Exception as ex:
            self.logger.warning("[中继] 读取卡下角色失败：%s", ex)
            return None
        if not names:
            self.logger.info("[中继] 卡内内容扫描：卡 %r 下没有可用角色，不猜", card_ref)
            return None
        return self._scan_messages_for_character_in(messages, names)

    def _scan_system_prompt_known_names(
        self,
        messages: Sequence[Dict[str, Any]],
        names: Optional[Sequence[Any]] = None,
        card: Any = None,
    ) -> Optional[str]:
        """3b：统计角色名在**第一条 system 消息**里出现的次数。

        **V5.9**：候选名单默认由 ``_character_candidates_for_scan(card)`` 给
        （【演员】 > 当前卡 > 全库），不再无脑全库扫；也可以由调用方显式传
        ``names``。候选为空 → 返回 ``None``，不猜。

        动机：Tavo / SillyTavern 每次请求都会把当前角色卡的完整介绍（人设、
        背景、关系描述）塞进 system prompt，主角名在其中反复出现，比对话
        正文稳定得多；这样用户**换卡时不需要改配置、不需要给每张卡配 URL**。

        两道保护（与 content_scan 完全一致，宁可返回 None 也不猜错）：

        * 最高分 < ``CONTENT_SCAN_MIN_SCORE``（默认 2）→ 不猜
        * 最高分与第二名差距 < 1（并列）→ 不猜

        本方法只读取、不注册角色；匹配是简单的 ``名字 in 文本``（区分大小写）。
        """
        try:
            system_text = ""
            for m in messages:
                if str(m.get("role", "")).strip().lower() == "system":
                    system_text = _relay_message_text(m)
                    break
            if not system_text:
                return None

            if names is not None:
                cand = [str(n).strip() for n in names
                        if str(n or "").strip() and not self._is_user_name(n)]
            else:
                cand = self._character_candidates_for_scan(card)
            if not cand:
                self.logger.info("[中继] 角色卡扫描：候选名单为空，不猜")
                return None

            counts: Dict[str, int] = {}
            for name in cand:
                hit = system_text.count(name)
                if hit:
                    counts[name] = counts.get(name, 0) + hit
            if not counts:
                return None

            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            top_name, top = ranked[0]
            second = ranked[1][1] if len(ranked) > 1 else 0
            if top < CONTENT_SCAN_MIN_SCORE:
                self.logger.info(
                    "[中继] 角色卡扫描最高分 %d（< %d）太弱，不猜：%s",
                    top, CONTENT_SCAN_MIN_SCORE, ranked[:3])
                return None
            if top - second < 1:
                self.logger.info("[中继] 角色卡扫描并列，不猜：%s", ranked[:3])
                return None
            self.logger.debug("[中继] 角色卡扫描得分：%s", ranked[:3])
            return top_name
        except Exception as ex:
            self.logger.warning("[中继] 角色卡扫描失败：%s", ex)
            return None

    def _scan_system_prompt_for_character(
        self,
        messages: Sequence[Dict[str, Any]],
    ) -> Optional[str]:
        """3c：从第一条 ``role=system`` 的 content 里抠角色名。"""
        system_text = ""
        for m in messages:
            if str(m.get("role", "")).strip().lower() == "system":
                system_text = _relay_message_text(m)
                break
        if not system_text:
            return None

        known = self.character_names_cached()
        for pat in SYSTEM_NAME_PATTERNS:
            try:
                matches = list(re.finditer(pat, system_text))
            except Exception:
                continue
            # 同一个模式可能有多处命中（"你是谁？你是乙。"）——逐个校验，
            # 前一个被当成代词丢掉时要继续往后找，别直接放弃这个模式。
            for mt in matches:
                cand = _relay_fix_text(mt.group(1)).strip().strip("「」『』\"'")
                if not cand:
                    continue
                # 已知角色名出现在候选里 -> 对齐到已知角色（取最长的那个）
                for name in sorted(known, key=len, reverse=True):
                    if name and name in cand:
                        return name
                if len(cand) > NAME_MAX_LEN or cand in NAME_REJECT_EXACT:
                    continue
                if cand.endswith("的") or any(p in cand
                                              for p in NAME_REJECT_PARTS):
                    continue
                return cand
        return None

    # ==================================================================
    # V3 追加：卡片层识别（先认卡、再认人）
    # ==================================================================
    def _scan_system_prompt_for_card(
        self,
        messages: Sequence[Dict[str, Any]],
    ) -> Optional[str]:
        """3b-卡：用 ``cards`` 表里的卡名去第一条 ``role=system`` 里做匹配。

        与 ``_scan_system_prompt_known_names()`` 同策略（复用
        ``card_names_cached()`` 与 ``CONTENT_SCAN_MIN_SCORE`` 阈值）：统计每个
        已知卡名在 system prompt 里出现的次数，取最多的那个；最高分 < 2 或与
        第二名并列 → 不猜（返回 None）。只读，不建卡。
        """
        try:
            system_text = ""
            for m in messages:
                if str(m.get("role", "")).strip().lower() == "system":
                    system_text = _relay_message_text(m)
                    break
            if not system_text:
                return None

            names = self.card_names_cached()
            if not names:
                return None

            counts: Dict[str, int] = {}
            for name in names:
                hit = system_text.count(name)
                if hit:
                    counts[name] = counts.get(name, 0) + hit
            if not counts:
                return None

            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            top_name, top = ranked[0]
            second = ranked[1][1] if len(ranked) > 1 else 0
            if top < CONTENT_SCAN_MIN_SCORE:
                self.logger.debug("[中继] 卡名扫描最高分 %d（< %d）太弱：%s",
                                  top, CONTENT_SCAN_MIN_SCORE, ranked[:3])
                return None
            if top - second < 1:
                self.logger.debug("[中继] 卡名扫描并列，不猜：%s", ranked[:3])
                return None
            self.logger.debug("[中继] 卡名扫描得分：%s", ranked[:3])
            return top_name
        except Exception as ex:
            self.logger.warning("[中继] 卡名扫描失败：%s", ex)
            return None

    def card_from_user_content(self, messages: Any) -> Optional[str]:
        """生图请求专用：从最后一条 user 的正文里扫库中已注册角色名，
        命中就反查它的 card_id。用于 system 为空、识别链全失败的裸 payload。
        只用于生图路径，不参与正常聊天。

        ★ 扫全文（不是前 80 字）：Tavo 生图模板把真正的请求文案放在末尾的
        ``User Request:`` 之后（实测位置 1833/1854），前 80 字全是英文模板
        说明，永远不含角色名。
        """
        try:
            last_user = ""
            for m in (messages or []):
                if (isinstance(m, dict)
                        and str(m.get("role", "")).strip().lower() == "user"):
                    last_user = _relay_message_text(m)
            if not last_user:
                return None
            head = last_user
            rows = self.db.query(
                "SELECT name, card_id FROM characters "
                "WHERE purged_at IS NULL AND is_user = 0 AND card_id IS NOT NULL"
            )
            best_name = ""
            best_cid = None
            for r in rows:
                nm = str(r.get("name") or "").strip()
                if not nm or len(nm) < 2 or len(nm) > 6:
                    continue
                if nm in head and len(nm) > len(best_name):
                    best_name = nm
                    best_cid = r.get("card_id")
            if best_cid is None:
                return None
            row = self.db.query(
                "SELECT name FROM cards WHERE card_id = ?", (best_cid,))
            if not row:
                return None
            self.logger.info(
                "[中继] 生图请求 user 扫卡：命中 %r → 卡 %r",
                best_name, row[0].get("name"))
            return str(row[0].get("name") or "").strip() or None
        except Exception as ex:
            self.logger.warning("[中继] user 扫卡失败：%s", ex)
            return None

    def _remember_request_user_name(self, name: Any) -> None:
        """把 Tavo system 里认出的用户昵称并入 ``memory.user_names``。

        并入之后，``_is_user_name()`` / ``MemoryManager._is_user_character()``
        以及 ``add_memory()`` 的守卫会自动把它当用户：
        **不建角色、不挂卡、不写记忆**。

        只改内存里的配置（``config.memory.user_names``），不写库、不改 yaml；
        作用范围是本进程 —— 用户在 Tavo 里的昵称本来就只有请求里才知道。
        """
        nm = _relay_fix_text(name).strip()
        if not nm:
            return
        try:
            cfg_mem = self.config.memory
        except Exception:
            return
        try:
            cur: List[str] = list(getattr(cfg_mem, "user_names", ()) or ())
            if isinstance(getattr(cfg_mem, "user_names", None), str):
                cur = [str(cfg_mem.user_names)]
            if nm in cur:
                return
            cur.append(nm)
            cfg_mem.user_names = tuple(cur)
            self.logger.info(
                "[中继] 认到用户昵称 %r，已并入用户名单（不建角色 / 不挂卡 / "
                "不建记忆），当前名单=%s", nm, list(cfg_mem.user_names))
        except Exception as ex:
            self.logger.warning("[中继] 记录用户昵称失败：%s", ex)

    def _detect_time_aware(self, messages: Any) -> bool:
        """**V5.6**：本轮这张卡开不开【时间感知】（开场白 / system 里的标记）。

        * 每轮都**先重置成 False**，再按标记结果设置 —— 换卡不会沿用上一张的
        * 标记写在角色卡开场白（system 或第一条 assistant）里：
            ``【时间感知】开`` -> True
            ``【时间感知】关`` -> False
            没有这个标记       -> False（默认关）
        * 返回值同时写进 ``self._current_time_aware``（跟 ``_current_card`` 同生命周期）
        """
        self._current_time_aware = False
        try:
            found = _scan_time_aware(messages)
        except Exception as ex:
            self.logger.warning("[中继] 时间感知标记识别失败：%s", ex)
            return False
        if found is None:
            return False
        self._current_time_aware = bool(found)
        self.logger.info("[中继] 开场白【时间感知】%s -> 本轮%s注入时间信息",
                         "开" if found else "关",
                         "" if found else "不")
        return self._current_time_aware

    def _time_aware_stamp(self, card: Any = None
                          ) -> Tuple[str, Optional[str]]:
        """取「现在」和「这张卡上次聊天时间」，并把标记刷成现在。

        返回 ``(now_iso, prev_iso或None)`` —— 只在时间感知开着时由
        ``build_context()`` 调用，所以标记粒度是「这张卡的对话」。
        """
        name = str(card or self._current_card or "").strip() or "-"
        key = TIME_AWARE_META_PREFIX + name
        now = now_iso()
        prev: Optional[str] = None
        try:
            prev = self.db.get_meta(key)
            if prev:
                prev = str(prev)
            self.db.set_meta(key, now)
        except Exception as ex:
            self.logger.warning("[中继] 时间感知标记读写失败：%s", ex)
        return now, prev

    def _scan_actor_names(self, messages: Any) -> List[str]:
        """**V5.8 / V5.10**：解析开场白 / system 里的角色名单标记。

        扫所有 ``role=system`` 的 content + 第一条 ``role=assistant``（开场白），
        支持下面几种写法（**V5.10 起**，解析细节见 ``_actor_names_from_text``）::

            【演员】角色E
            【演员】角色E、角色F、明
            【登场人物】                      <- 标记单独成行
            - 角色A：住在主角隔壁的少女，爱聊八卦。
            - 角色F：儿子。

        返回**去重、保持出现顺序**的名字列表（不做任何过滤 —— 用户 / 卡名的
        过滤交给调用方 ``_should_skip_character``）。
        """
        texts: List[str] = []
        first_assistant = ""
        try:
            for m in (messages or []):
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "").strip().lower()
                if role not in ("system", "assistant"):
                    continue
                txt = _relay_message_text(m)
                if not txt:
                    continue
                if role == "system":
                    texts.append(txt)
                elif not first_assistant:
                    first_assistant = txt
        except Exception as ex:
            self.logger.warning("[中继] 读取【演员】输入失败：%s", ex)
            return []
        if first_assistant:
            texts.append(first_assistant)

        names: List[str] = []
        for txt in texts:
            # [规则文本过滤] 卡规则 / 客户端提示块里列的「角色清单」不算名单 ——
            # 它会照着自己写的角色表把已删角色重新建出来（删了又回来）。
            # ★ 第一条 assistant（开场白）是用户自己写的，不做脚手架过滤
            _is_first_assistant = (txt == first_assistant)
            if _is_card_rule_text(txt):
                continue
            if _is_scaffold_text(txt) and not _is_first_assistant:
                continue
            try:
                # V5.10：解析细节统一收进 _actor_names_from_text
                #       （行内【演员】… + 标题式【登场人物】下面几行）
                for nm in _actor_names_from_text(txt):
                    if nm not in names:
                        names.append(nm)
            except Exception as ex:
                self.logger.warning("[中继] 解析【演员】/【登场人物】失败：%s", ex)
                continue
        return names

    def all_character_aliases(self, card_ref: Any = None) -> List[str]:
        """[V2.3 别名映射] 全库角色的所有别名（去重、去空白）。"""
        cid = None
        if card_ref is not None and str(card_ref).strip():
            cid = self.card_mgr._resolve_card_id(card_ref)
            if cid is None:
                return []
        try:
            if cid is not None:
                rows = self.db.query(
                    "SELECT aliases FROM characters WHERE purged_at IS NULL AND card_id = ?",
                    (cid,))
            else:
                rows = self.db.query(
                    "SELECT aliases FROM characters WHERE purged_at IS NULL")
        except Exception as ex:
            self.logger.warning("[识别] 取别名失败：%s", ex)
            return []
        seen: List[str] = []
        for r in rows:
            for a in _as_list(r.get("aliases")):
                sa = str(a).strip()
                if sa and sa not in seen:
                    seen.append(sa)
        return seen

    def _character_candidates_for_scan(self, card: Any = None, only_active: bool = False) -> List[str]:
        """**V5.9**：本次「该被扫描」的角色候选名单（唯一入口）。

        收窄顺序：

        1. ``self._current_card_actors`` 非空 → **就用它**（开场白【演员】是权威声明）
        2. 否则卡已识别（``card`` 参数或 ``self._current_card``）→ 该卡下已登记的角色
        3. 都没有 且 卡未知 → 全库角色（V5.9.1：卡已知但本卡空 → 返回空）

        **V2.3 / V5.9.2**：名单最后补上 ``all_character_aliases(cname)`` —— 只补本卡别名。
        Tavo 只写「爸爸」时，它得先成为候选，后面的别名映射才可能命中真名「山田一郎」。

        返回的名单一律**剔除用户身份**（``明`` / ``User`` 不该当说话人）。
        名单为空时调用方直接返回 ``None``，**不猜**。

        注意：``card`` 参数是必须的 —— 识别过程中 ``self._current_card`` 还是
        上一轮的值（要到识别结束才写），所以扫描步骤一律显式传当前 ``card``。
        """
        out: List[str] = []
        cname = str(card or self._current_card or "").strip()
        try:
            if self._current_card_actors:
                out = [str(a).strip() for a in self._current_card_actors]
            elif cname:
                out = [str(n).strip() for n in self._card_character_names(cname)]
        except Exception as ex:
            self.logger.warning("[中继] 取扫描候选失败：%s", ex)
            out = []
        if not out:
            try:
                # V5.9.1: 只有 card 未知时才用全库；card 已知但本卡空 → 返回空
                if not cname:
                    out = [str(n).strip() for n in self.character_names_cached()]
            except Exception:
                out = []
        try:
            for _a in self.all_character_aliases(cname):      # [V2.3] 别名进候选
                if _a and _a not in out:
                    out.append(_a)
        except Exception:
            pass
        result = [n for n in out if n and not self._is_user_name(n)]
        if only_active:
            result = self._filter_active_only(result, cname)
        return result

    def _filter_active_only(self, cands, card):
        """只保留"出过场"的角色名（有消息 或 有记忆）。
        不在 characters 表里的名字（别名等）原样保留。
        查库失败 → 退回原列表（不阻断识别）。"""
        if not cands:
            return cands
        try:
            _cid = self.card_mgr._resolve_card_id(card)
        except Exception:
            return cands
        if _cid is None:
            return cands
        try:
            rows = self.db.query(
                "SELECT name FROM characters c "
                "WHERE c.card_id = ? AND c.purged_at IS NULL "
                "AND NOT ("
                "  EXISTS(SELECT 1 FROM messages m WHERE m.character_id = c.character_id) "
                "  OR EXISTS(SELECT 1 FROM memories mm WHERE mm.owner_character_id = c.character_id)"
                ")",
                (_cid,))
        except Exception as ex:
            self.logger.warning("[中继] 活跃候选查询失败：%s", ex)
            return cands
        inactive = set()
        for r in rows:
            n = _relay_fix_text(r.get("name")).strip()
            if n:
                inactive.add(n)
        if not inactive:
            return cands
        return [n for n in cands if n not in inactive]

    def _scan_declared_card_name(self, messages: Any) -> Optional[str]:
        """**V5.8**：本地解析开场白 / system 里的 ``【卡名】XXX``。

        库里没有这张卡时，以前只能靠 LLM 兜底认卡（``auto_detect_card=false``
        就认不出）。有了这个，卡片名是用户明确写的，本地直接采信。

        扫所有 ``role=system`` + 第一条 ``role=assistant``，取**最后一个**标记
        （同一条文本里写多次时，后面写的算修正）。
        """
        texts: List[str] = []
        first_assistant = ""
        try:
            for m in (messages or []):
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "").strip().lower()
                if role not in ("system", "assistant"):
                    continue
                txt = _relay_message_text(m)
                if not txt:
                    continue
                if role == "system":
                    texts.append(txt)
                elif not first_assistant:
                    first_assistant = txt
        except Exception as ex:
            self.logger.warning("[中继] 读取【卡名】失败：%s", ex)
            return None
        if first_assistant:
            texts.append(first_assistant)
        found: Optional[str] = None
        for txt in texts:
            try:
                hits = list(CARD_MARK_RE.finditer(txt))
            except Exception:
                continue
            for mt in hits:
                nm = _relay_fix_text(mt.group(1)).strip()
                nm = nm.strip("「」『』\"'“”").rstrip("。.!！?？；;")
                if nm and len(nm) <= NAME_MAX_LEN:
                    found = nm
        return found

    def _apply_card_actors(self, messages: Any, card: Any = None) -> List[str]:
        """**V5.8**：卡已知时把开场白的【演员】名单落地。

        * 名单里的每个名字 ``get_or_create`` 并挂到**当前卡**下
          （过 ``_should_skip_character``：卡名 / 用户不建档、不挂钩；
           已经属于别卡的角色也不抢 —— 与 V5.7 同一道闸）
        * 名单存 ``self._current_card_actors``（跟 ``_current_card`` 同生命周期）
        * 这是**已知名单**不是白名单：没列过的名字（剧情里冒出来的）照常能建档
        * 同一轮内重复调用不重复干活（已有名单直接返回）
        """
        if not card:
            return []
        if self._current_card_actors:
            return list(self._current_card_actors)
        try:
            names = self._scan_actor_names(messages)
        except Exception as ex:
            self.logger.warning("[中继] 解析【演员】失败：%s", ex)
            return []
        if not names:
            return []
        self._current_card_actors = list(names)
        self.logger.info("[中继] 开场白【演员】= %s", list(names))
        for nm in names:
            if self._should_skip_character(nm, card):
                self.logger.info("[中继] 【演员】%r 命中用户/卡名过滤，不建档、不挂钩",
                                 nm)
                continue
            try:
                row = self.char_mgr.get_or_create(nm)
                if row is None:
                    continue
                real = str(row.get("name") or nm)
                self.remember_character_name(real)
                _other = self._other_card_of_character(real, card)
                if _other:
                    self.logger.info("[中继] 【演员】%r 已属于卡 %r，不抢过来"
                                     "（跳过挂钩）", real, _other)
                    continue
                self.card_mgr.attach_character(card, real)
            except Exception as ex:
                self.logger.warning("[中继] 【演员】建档 %r 失败：%s", nm, ex)
        return list(names)

    def _alias_resolve(self, card: Any, speaker: Any) -> Tuple[str, str]:
        """[V2.3 别名映射] 把「称呼 / 别名」映射回真名（零 token、纯查库）。

        * 卡名：``CardManager.resolve_by_alias``（真名 → 别名）
        * 说话人：``CharacterManager.resolve_name``（id / 真名 / 别名）
        * 说话人解析出来后，若卡还没定，用 ``card_of_character`` 反查它挂的卡

        返回 ``(真卡名, 真角色名)``；解析不到返回空串（调用方保持原值）。
        """
        out_card = ""
        out_spk = ""
        try:
            nm = "" if isinstance(card, (int, float)) else str(card or "").strip()
            if nm:
                out_card = self.card_mgr.resolve_by_alias(nm) or ""
        except Exception as ex:
            self.logger.warning("[识别] 别名映射(卡)失败：%s", ex)
        try:
            nm2 = "" if isinstance(speaker, (int, float)) else str(speaker or "").strip()
            if nm2:
                out_spk = self.char_mgr.resolve_name(nm2) or ""
        except Exception as ex:
            self.logger.warning("[识别] 别名映射(角色)失败：%s", ex)
        if out_spk and not out_card:
            try:
                pc = self.card_mgr.card_of_character(out_spk)
                if pc:
                    out_card = str(pc.get("name") or "")
            except Exception:
                pass
        return out_card, out_spk

    def _is_bare_kinship(self, name: Any) -> bool:
        """[V2.4 兜底防呆] 这个名字是不是**纯称呼**（爸爸/哥哥/女儿…）。"""
        nm = _relay_fix_text(name).strip() if not isinstance(name, (int, float)) else ""
        return bool(nm) and nm in KINSHIP_ADDRESS_WORDS

    def _refuse_bare_kinship(self, name: Any, where: str) -> bool:
        """纯称呼**拒绝建档**并告警；返回 True = 已拒绝（调用方直接跳过）。

        先按真名 + 别名解析：能解析到已有角色就不算"纯称呼"（说明用户已经
        在 UI 里把它配成别名了 → 正常走别名映射）。
        """
        nm = _relay_fix_text(name).strip() if not isinstance(name, (int, float)) else ""
        if not nm or not self._is_bare_kinship(nm):
            return False
        try:
            if self.char_mgr.resolve_name(nm):
                return False
        except Exception:
            pass
        self.logger.warning(
            "[识别] 拒绝为纯称呼 %r 建档（%s）：它不是角色名。"
            "若它确实指某个角色，请在 UI 里把该角色加别名 %r，引擎会自动映射。",
            nm, where, nm)
        return True

    def _name_in_vocative_position(self, msg: str, name: str) -> bool:
        """角色名是否处于"呼语"位置 —— 用户在对他说，不是提他。

        判据：名字出现在消息开头附近，且名字后紧跟：
              呼语标点（，,：:？！?!、）或第二人称代词（你/您）。
        [10-04 更新] 加"你/您"；前缀放宽到 4 字；遍历所有出现位置。
        """
        t = str(msg or "")
        if not t or not name:
            return False
        _voc_tail = "，,：:？！?!、你您"
        _voc_verbs = ("过来",)
        _neg_before_verbs = re.compile(r"[让叫请使使命要]")
        _max_prefix = 4
        _start = 0
        while True:
            pos = t.find(name, _start)
            if pos < 0:
                break
            _start = pos + 1
            prefix_clean = re.split(r"[，,。.！!？?；;：:\n]", t[:pos])[-1].strip(" \t\n\r")
            if len(prefix_clean) > _max_prefix:
                continue
            tail = t[pos + len(name):]
            if not tail:
                continue
            if tail[0] in _voc_tail:
                return True
            for _vb in _voc_verbs:
                if tail.startswith(_vb) and not _neg_before_verbs.search(t[:pos]):
                    return True
        return False

    def _should_skip_character(self, name: Any, card: Any = None) -> bool:
        """V3 统一判定：这个名字**该不该作为角色**（True = 不该）。

        命中任一条件即为 True —— 不建角色、不挂卡、不写认知
        （记忆 / 信念 / 知识 / 秘密 / 状态）：

        a) ``name == card`` —— **卡名不是角色**（如「某卡」只是卡名）
        b) ``name`` 命中 ``config.memory.user_names``（如 'User'、'明'）
        c) ``name`` 是库里 ``is_user = 1`` 的现有角色
        d) ``name`` 是 Tavo system 里 ``chat between X and Y`` 的 Y
           （已由 ``_remember_request_user_name()`` 并进 user_names）

        ``card`` 为空时退回 ``self._current_card``（本次请求的卡名）。
        """
        nm = _relay_fix_text(name).strip()
        if not nm:
            return True
        cname = _relay_fix_text(card).strip() if card else ""
        if not cname:
            cname = str(self._current_card or "").strip()
        if cname and nm == cname:
            return True
        return bool(self._is_user_name(nm))

    def _load_request_user_names(self, msgs: Any) -> List[str]:
        """[V2.6 动态用户识别] 从开场白 / 系统提示里解析【user】= 玩家名单。

        * 解析结果存进 ``self._request_user_names``（**本轮请求**用）；
        * 优先级**高于** ``config.yaml`` 的 ``user_names`` —— 写了【user】就仅以它为准；
        * 解析不到 → 置空列表，``_is_user_name`` 会退回 config（见 SPEC 1.4）。

        同时在 ``_detect_character_from_request`` 与 ``_detect_card_and_speaker``
        **两处入口**都调用，避免命中哪条快路径都能生效。
        """
        try:
            _ubuf = [_relay_message_text(m) for m in (msgs or [])
                     if str((m or {}).get("role", "")).strip().lower()
                     in ("system", "assistant")]
            _joined = "\n".join([x for x in _ubuf if x])
            self._request_user_names = _user_names_from_text(_joined)
            if self._request_user_names:
                self.logger.info(
                    "[识别] 动态玩家名单（来自开场白/系统提示【user】=，优先于 "
                    "config.user_names）：%s", "、".join(self._request_user_names))
            elif re.search(r"【\s*(?:user|玩家|用户)", _joined, re.I):
                # 有【user】字样却没解析出名字 → 格式不对，把原文打出来便于排查
                self.logger.warning(
                    "[识别] 发现疑似【user】标记但没解析出名字（格式应为"
                    "【user】=名字1，名字2）：%s", _joined[:200])
        except Exception as ex:
            self._request_user_names = []
            self.logger.warning("[识别] 解析动态玩家名单失败：%s", ex)
        return list(self._request_user_names)

    def _is_user_name(self, name: Any) -> bool:
        """V3：这个名字是不是「用户」（``is_user=1`` 或命中 ``memory.user_names``）。

        用于两处：LLM 识别出的 ``user`` 角色自动打标；自动挑主角时跳过用户。
        """
        nm = _relay_fix_text(name).strip()
        if not nm:
            return False
        try:
            row = self.char_mgr.get(nm)
            if row is not None and bool(row.get("is_user")):
                return True
        except Exception:
            pass
        # ---- [V2.6 动态用户识别] 开场白/系统提示里【user】= 解析出来的名单 ----
        # **优先级高于 config.yaml 的 user_names**（它是针对这张卡定制的）；
        # 当前请求没解析到就看这张卡上一次落库的名单（异步回写时仍能判定）。
        dyn: List[str] = list(getattr(self, "_request_user_names", []) or [])
        if not dyn:
            try:
                cur_card = str(getattr(self, "_current_card", "") or "").strip()
                if cur_card:
                    _raw = self.db.get_meta("card_user_names:" + cur_card)
                    if _raw:
                        dyn = [str(x) for x in (json.loads(_raw) or [])]
            except Exception:
                dyn = []
        if dyn:
            return nm in dyn
        try:
            wanted = getattr(self.config.memory, "user_names", ()) or ()
            if isinstance(wanted, str):
                wanted = (wanted,)
            return nm in tuple(str(w).strip() for w in wanted)
        except Exception:
            return False

    def _card_character_names(self, card_ref: Any) -> List[str]:
        """某张卡下已登记的角色名（长的排前面，便于"最长匹配优先"）。"""
        cid = self.card_mgr._resolve_card_id(card_ref)
        if cid is None:
            return []
        try:
            rows = self.db.query(
                "SELECT name FROM characters WHERE card_id = ? "
                "AND purged_at IS NULL", (cid,))
        except Exception as ex:
            self.logger.warning("[中继] 读取卡下角色失败：%s", ex)
            return []
        names = [_relay_fix_text(r.get("name")).strip() for r in rows]
        names = [n for n in names if n]
        return sorted(names, key=len, reverse=True)

    def _present_names_from_db(self, card_ref: Any = None,
                               limit: int = 10) -> List[str]:
        """最近 limit 条消息里出现过的本卡角色名（不含 User）。

        数据源 = messages 表（中继 payload 是 OpenAI 格式、没有 name 字段，
        所以不能从 payload 取）。JOIN characters 只为筛"属于本卡"。
        """
        cid = self.card_mgr._resolve_card_id(card_ref)
        if cid is None:
            return []
        try:
            rows = self.db.query(
                "SELECT m.name, m.is_user FROM messages m "
                "JOIN characters c ON c.character_id = m.character_id "
                "WHERE c.card_id = ? AND c.purged_at IS NULL "
                "ORDER BY m.send_date DESC, m.message_id DESC LIMIT ?",
                (cid, limit))
        except Exception as ex:
            self.logger.warning("[中继] 取在场名单失败：%s", ex)
            return []
        seen: List[str] = []
        for r in rows:
            if r.get("is_user"):
                continue
            nm = _relay_fix_text(r.get("name")).strip()
            if nm and nm not in seen:
                seen.append(nm)
        return seen

    def _extraction_roster_text(self) -> str:
        """抽取 prompt 用的「本轮涉及的角色」清单（本卡角色 + 规范名）。

        ``MemoryExtractor._build_user_prompt`` 是纯函数、拿不到库；名单在这里
        （有 card_mgr / db 的地方）算好，作为字符串传下去。取不到卡名、或本卡
        没有角色时返回 ""，prompt 保持原样 —— 宁可少一段，不要报错。
        """
        try:
            card = str(self._current_card or "").strip()
            cid = self.card_mgr._resolve_card_id(card) if card else None
            if cid is None:
                return ""
            rows = self.db.query(
                "SELECT name, role_type, static_profile, is_user FROM characters "
                "WHERE card_id = ? AND purged_at IS NULL "
                "ORDER BY CASE role_type WHEN 'main_character' THEN 3 "
                "WHEN 'npc' THEN 2 WHEN 'user' THEN 1 ELSE 0 END DESC, "
                "character_id ASC", (cid,))
            lines: List[str] = []
            _seen: set = set()
            used = 0
            for r in rows[:ROSTER_MAX_CHARACTERS]:
                nm = _relay_fix_text(r.get("name")).strip()
                if not nm:
                    continue
                if _to_int(r.get("is_user")):
                    tag = "（玩家）"
                else:
                    _rt = str(r.get("role_type") or "").strip()
                    tag = ("（%s）" % _rt) if _rt else ""
                line = "  - %s%s" % (nm, tag)
                lines.append(line)
                _seen.add(nm)
                used += len(line)
                if used > ROSTER_MAX_CHARS:
                    break
            # 玩家角色不挂卡（card_id 为 NULL），按卡取不到 → 单独补一行
            try:
                _u = self.char_mgr.get_user()
            except Exception:
                _u = None
            if _u:
                _un = _relay_fix_text(_u.get("name")).strip()
                if _un and _un not in _seen:
                    lines.append("  - %s（玩家）" % _un)
            if not lines:
                return ""
            return ("【本轮涉及的角色】\n"
                    + "\n".join(lines) + "\n"
                    + "请只使用上表中的规范角色名；不要用「妈妈」「妹妹」这类称谓。\n\n")
        except Exception as ex:
            self.logger.warning("[抽取] 组装本卡角色清单失败（忽略）：%s", ex)
            return ""

    def _card_main_character(self, card_ref: Any,
                             strict: bool = False) -> Optional[str]:
        """某张卡的 ``main_character``（跳过用户）。

        ``strict=True``：[V2.5] **只认** ``role_type='main_character'`` 的角色，
        没有就返回 ``None``（供「卡牌强制主角」判断"这张卡到底有没有绑定主角"）。
        默认 ``strict=False`` 保留旧行为：没有就退第一个非 user 角色。
        """
        cid = self.card_mgr._resolve_card_id(card_ref)
        if cid is None:
            return None
        try:
            rows = self.db.query(
                "SELECT name, role_type, is_user FROM characters "
                "WHERE card_id = ? AND is_user = 0 "
                "ORDER BY CASE role_type WHEN 'main_character' THEN 0 "
                "         WHEN 'npc' THEN 1 ELSE 2 END, "
                "         message_count DESC, name ASC LIMIT 5", (cid,))
        except Exception as ex:
            self.logger.warning("[中继] 读取卡主角失败：%s", ex)
            return None
        for r in rows:
            nm = _relay_fix_text(r.get("name")).strip()
            if not nm:
                continue
            if strict and str(r.get("role_type") or "") != ROLE_MAIN:
                return None          # [V2.5] 严格模式：没绑定主角就是没有
            # V3：名字在「用户名单」里的（比如「明」）不算主角
            if self._is_user_name(nm):
                continue
            return nm
        return None

    def _llm_detect_card(
        self,
        messages: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """第 4 级：调一次 LLM 兜底识别卡 / 说话人 / 人物表。

        输入 = system prompt 前 ``LLM_CARD_DETECT_SYSTEM_CHARS`` 字
               + 最近 ``LLM_CARD_DETECT_MSG_COUNT`` 条消息（每条正文前
                 ``LLM_CARD_DETECT_MSG_CHARS`` 字）

        system prompt 用 ``LLM_CARD_DETECT_SYSTEM``（V3 规范原文）。
        任何失败（未启用 / 返回 None / 解析失败 / 抛异常）都返回 None，
        **绝不中断请求**。本方法只做"识别"，不写库（写库在
        ``_apply_llm_detection()``）。
        """
        try:
            if self.llm is None or not getattr(self.llm, "enabled", False):
                return None

            system_text = ""
            for m in messages:
                if str(m.get("role", "")).strip().lower() == "system":
                    system_text = _relay_message_text(m)
                    break

            tail: List[Dict[str, Any]] = []
            for m in list(messages)[-LLM_CARD_DETECT_MSG_COUNT:]:
                if not isinstance(m, dict):
                    continue
                tail.append({
                    "role": str(m.get("role") or ""),
                    "name": str(m.get("name") or ""),
                    "content": _relay_message_text(m)[:LLM_CARD_DETECT_MSG_CHARS],
                })

            user_prompt = (
                "【system 提示词（前 %d 字）】\n%s\n\n"
                "【最近 %d 条消息】\n%s"
                % (LLM_CARD_DETECT_SYSTEM_CHARS,
                   system_text[:LLM_CARD_DETECT_SYSTEM_CHARS],
                   len(tail),
                   json.dumps(tail, ensure_ascii=False, indent=1)))

            data = self.llm.chat_json(LLM_CARD_DETECT_SYSTEM, user_prompt)
            if not isinstance(data, dict):
                self.logger.info("[中继] LLM 兜底：返回不是 JSON 对象，放弃")
                return None

            def _clean(value: Any, limit: int = NAME_MAX_LEN) -> Optional[str]:
                txt = _relay_fix_text(value).strip().strip("「」『』\"'")
                if not txt or txt.lower() in ("null", "none", "unknown", "无"):
                    return None
                return txt[:limit]

            card = _clean(data.get("card"))
            speaker = _clean(data.get("speaker"))

            chars: List[Dict[str, Any]] = []
            raw_chars = data.get("characters")
            if isinstance(raw_chars, list):
                for item in raw_chars:
                    if isinstance(item, dict):
                        nm = _clean(item.get("name"))
                        rt = str(item.get("role_type") or "").strip().lower()
                    elif isinstance(item, str):
                        nm, rt = _clean(item), ""
                    else:
                        continue
                    if not nm:
                        continue
                    if rt not in VALID_ROLE_TYPES:
                        rt = ROLE_MAIN
                    if all(c["name"] != nm for c in chars):
                        chars.append({"name": nm, "role_type": rt})
            if speaker and all(c["name"] != speaker for c in chars):
                chars.append({"name": speaker, "role_type": ROLE_MAIN})

            # ---- V3 过滤：**卡名不是角色** + 用户不是角色 ----
            # 命中任一即剔除：a) name == card  b) config.memory.user_names
            # c) 库里 is_user=1  d) Tavo 的 chat-between 昵称
            dropped: List[str] = []
            kept: List[Dict[str, Any]] = []
            for c in chars:
                if self._should_skip_character(c.get("name"), card):
                    dropped.append(str(c.get("name")))
                else:
                    kept.append(c)
            chars = kept
            if dropped:
                self.logger.info("[中继] LLM 兜底：剔除卡名/用户 %s，保留 %s",
                                 dropped, [c["name"] for c in chars])

            # ---- V3 speaker 修正：被过滤掉（如 speaker == card）就从剩下的角色里挑
            if speaker and self._should_skip_character(speaker, card):
                self.logger.info(
                    "[中继] LLM 兜底：speaker=%r 被过滤（卡名/用户），"
                    "改从角色列表里挑", speaker)
                speaker = None
            if not speaker and chars:
                mains = [c["name"] for c in chars
                         if str(c.get("role_type") or "") == ROLE_MAIN]
                speaker = str(mains[0]) if mains else str(chars[0]["name"])
                self.logger.info(
                    "[中继] LLM 兜底：speaker 改为 %r（优先 main_character）",
                    speaker)

            if not card and not speaker and not chars:
                self.logger.info("[中继] LLM 兜底：全是 null，放弃")
                return None
            return {"card": card, "speaker": speaker, "characters": chars}
        except Exception as ex:
            self.logger.warning("[中继] LLM 兜底识别失败：%s", ex)
            return None

    def _other_card_of_character(self, name: Any, card: Any) -> Optional[str]:
        """**V5.7**：这个角色是不是已经归属**另一张卡**了？是则返回那张卡名。

        * 角色不存在 / card_id 为空（散装）/ 本来就属于 ``card`` -> ``None``
        * 用途：LLM 兜底（还有别处）**不许把别张卡的角色抢过来**——
          否则「小女友」卡会把「角色E」从「严厉教师」卡下拽走，
          连带那角色的全部记忆一起串卡。
        """
        try:
            nm = _relay_fix_text(name).strip()
            cn = _relay_fix_text(card).strip()
            if not nm or not cn:
                return None
            row = self.char_mgr.get(nm)
            if row is None or not row.get("card_id"):
                return None
            pc = self.card_mgr.card_of_character(nm)
            pname = str((pc or {}).get("name") or "").strip()
            if pname and pname != cn:
                return pname
        except Exception as ex:
            self.logger.warning("[中继] 判断角色归属失败：%s", ex)
        return None

    def _apply_llm_detection(
        self,
        res: Dict[str, Any],
    ) -> Dict[str, Any]:
        """把 LLM 兜底识别结果落库（建卡 + 建角色 + 挂卡 + 定角色类型）。

        严格按 V3 规范 2.3 的 5 步；每一步独立 try/except，失败只记日志。
        返回规范后的 ``{"card","speaker","characters"}``。
        """
        card_name = _relay_fix_text(res.get("card")).strip() or None
        speaker = _relay_fix_text(res.get("speaker")).strip() or None
        raw_chars = [c for c in (res.get("characters") or [])
                     if isinstance(c, dict) and c.get("name")]
        out_chars: List[Dict[str, Any]] = []

        # ---- 1) 卡 ----
        if card_name:
            try:
                if self.card_mgr.get_or_create(card_name, source=CARD_SOURCE_LLM):
                    self.remember_card_name(card_name)
            except Exception as ex:
                self.logger.warning("[中继] LLM 兜底：建卡失败：%s", ex)

        # ---- 2) 角色逐个建档 + 挂到卡上 ----
        for item in raw_chars:
            nm = _relay_fix_text(item.get("name")).strip()
            if not nm:
                continue
            # V3 双重保险：卡名 / 用户不建档、不挂卡（上面已过滤过一遍）
            if self._should_skip_character(nm, card_name):
                self.logger.info("[中继] LLM 兜底：跳过 %r（卡名/用户，"
                                 "不建档 / 不挂卡）", nm)
                continue
            # V5.7：已经属于**别的卡**的角色不许抢过来（防串卡）
            _other = self._other_card_of_character(nm, card_name)
            if _other:
                self.logger.info("[中继] LLM 兜底：跳过 %r（已属于卡 %r，"
                                 "不抢过来、不挂钩）", nm, _other)
                continue
            rt = str(item.get("role_type") or ROLE_MAIN).strip().lower()
            if rt not in VALID_ROLE_TYPES:
                rt = ROLE_MAIN
            try:
                row = self.char_mgr.get_or_create(nm)
                if row is None:
                    continue
                real = str(row.get("name") or nm)
                self.remember_character_name(real)
                # ---- 3) role_type='user'（或命中 user_names）-> is_user=1 ----
                if rt == ROLE_USER or self._is_user_name(real):
                    rt = ROLE_USER
                    try:
                        self.set_role(real, ROLE_USER)
                    except Exception as ex:
                        self.logger.warning("[中继] LLM 兜底：置 user 失败：%s", ex)
                elif str(row.get("role_type") or "") in ("", ROLE_UNKNOWN):
                    try:
                        self.char_mgr.set_role(real, rt)
                    except Exception as ex:
                        self.logger.warning("[中继] LLM 兜底：置角色类型失败：%s",
                                            ex)
                if card_name:
                    self.card_mgr.attach_character(card_name, real)
                out_chars.append({"name": real, "role_type": rt})
            except Exception as ex:
                self.logger.warning("[中继] LLM 兜底：建档 %r 失败：%s", nm, ex)

        # ---- 4) speaker 不在 characters 里 -> 补一个 main_character ----
        # V3：speaker 是卡名 / 用户时**不建档**，改从已建好的角色里挑
        # V5.7：LLM 给的说话人若已经属于**别的卡**，不抢、不用
        if speaker:
            _other_spk = self._other_card_of_character(speaker, card_name)
            if _other_spk:
                self.logger.info("[中继] LLM 兜底：speaker=%r 已属于卡 %r，"
                                 "不抢过来（本轮改用卡下已有角色）",
                                 speaker, _other_spk)
                speaker = None
        # V5.9：开场白写了【演员】→ LLM 给的说话人若是「库里已存在的角色」却不在
        #       名单里，多半是认错了（历史残留），弃用；名单外的**新名字**
        #       （剧情里冒出来的新人）照收 —— 【演员】是已知名单不是白名单。
        if speaker and self._current_card_actors:
            try:
                _cands = list(self._character_candidates_for_scan(card_name))
                # 本卡下的角色也算「已知」（剧情里冒出来、已经挂在本卡的人）
                if card_name:
                    for _n in self._card_character_names(card_name):
                        if _n and _n not in _cands:
                            _cands.append(_n)
                if _cands and speaker not in _cands \
                        and self.char_mgr.get(speaker) is not None:
                    self.logger.info(
                        "[中继] LLM 兜底：speaker=%r 不在【演员】名单 %s 里"
                        "（且是库里已有的角色），弃用", speaker, _cands)
                    speaker = None
            except Exception as ex:
                self.logger.warning("[中继] LLM 兜底：演员名单校验失败：%s", ex)
        if speaker and self._should_skip_character(speaker, card_name):
            self.logger.info("[中继] LLM 兜底：speaker=%r 是卡名/用户，不建档",
                             speaker)
            speaker = None
        if not speaker and out_chars:
            _mains = [c["name"] for c in out_chars
                      if str(c.get("role_type") or "") == ROLE_MAIN]
            speaker = str(_mains[0]) if _mains else str(out_chars[0]["name"])
            self.logger.info("[中继] LLM 兜底：speaker 回落为 %r", speaker)
        if speaker:
            try:
                row = self.char_mgr.get_or_create(speaker)
                if row is not None:
                    real = str(row.get("name") or speaker)
                    self.remember_character_name(real)
                    # AI 正在扮演的那个角色 -> main_character
                    # （用户 / 已定好的角色不覆盖）
                    cur_rt = str(row.get("role_type") or "")
                    if not self._is_user_name(real) \
                            and cur_rt not in (ROLE_USER, ROLE_MAIN):
                        try:
                            pass  # [禁用自动升主角] 用户要求所有非用户角色保持 npc
                        except Exception:
                            pass
                    if card_name:
                        self.card_mgr.attach_character(card_name, real)
                    if all(c["name"] != real for c in out_chars):
                        out_chars.append({"name": real,
                                          "role_type": ROLE_MAIN})
                    speaker = real
            except Exception as ex:
                self.logger.warning("[中继] LLM 兜底：说话人建档失败：%s", ex)

        # 卡下角色以数据库为准（顺序：user -> main -> npc -> 其他）
        if card_name:
            try:
                rows = self.card_mgr.list_characters(card_name)
                if rows:
                    out_chars = [{"name": r.get("name"),
                                  "role_type": r.get("role_type")}
                                 for r in rows]
            except Exception as ex:
                self.logger.warning("[中继] LLM 兜底：回读卡下角色失败：%s", ex)

        return {"card": card_name, "speaker": speaker, "characters": out_chars}

    def _reselect_speaker(self, card: Any,
                          chars: Optional[Sequence[Any]] = None
                          ) -> Optional[str]:
        """**V5.1**：speaker 被判为「用户 / 卡名」后，从卡下角色里改选。

        顺序：``main_character`` -> 卡下第一个非 user 角色 -> 卡的 main_character
        （库里查）；都没有返回 ``None``（宁可识别不出，也不拿用户当说话人）。
        """
        try:
            items = [c for c in (chars or []) if isinstance(c, dict)]
            mains = [str(c.get("name")) for c in items
                     if str(c.get("role_type") or "") == ROLE_MAIN
                     and str(c.get("name") or "").strip()]
            if mains:
                return mains[0].strip()
            for c in items:
                nm = str(c.get("name") or "").strip()
                if nm and not self._is_user_name(nm):
                    return nm
            if card:
                mc = str(self._card_main_character(card) or "").strip()
                if mc and not self._is_user_name(mc):
                    return mc
        except Exception as ex:
            self.logger.warning("[中继] speaker 改选失败：%s", ex)
        return None

    def _detect_card_and_speaker(
        self,
        messages: Any,
        qs: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """V3 主识别入口：**先认卡，再认说话人**。

        返回 ``{"card","speaker","characters","source"}``：

        * ``card``       —— 卡名（作品 / 场景 / 设定集），识别不出为 None
        * ``speaker``    —— 当前 AI 正在扮演的那个角色名
        * ``characters`` —— 该卡下已知的角色 ``[{"name","role_type"}, ...]``
        * ``source``     —— query / header / local_scan / llm_fallback /
                            default / resolve_active / none

        识别优先级（第一个命中就用，**每一步单独 try/except，失败继续下一步**）：::

            1. URL query    ?card= / ?card_name= ；?char= / ?character= 作为说话人
            2. Header       X-Card ；X-Character 作为说话人
            3. 本地扫描     3a assistant.name -> 反查卡
                            3b system 扫已知卡名；再扫角色名（须属于该卡）
                            3c 沿用 system prompt 抠名字 -> 反查卡
            4. LLM 兜底     库里认不出且 llm.enabled + auto_detect_card
            5. 配置兜底     config.llm.default_card / default_character
            6. 活跃兜底     engine.resolve_active()

        结果同时写进 ``self.last_card_detect``。
        """

        _multi_hit_round = False  # 3a-new 多角色命中（不猜）标记，供末尾兜底日志用
        card: Optional[str] = None
        speaker: Optional[str] = None
        source: str = DETECT_SOURCE_NONE
        msgs = [m for m in (messages or []) if isinstance(m, dict)]

        # [V2.6 动态用户识别] 开场白/系统提示里的【user】= 玩家名单（优先于 config）
        self._load_request_user_names(msgs)

        # 注：识别入口的诊断日志（"[中继] 识别输入 ..."）已上移到公共前置
        # ``_relay_prepare()``，级别 INFO，非流式 / 流式、开不开注入都会打。

        # ---- 0) V3：先从 system 里认出「用户昵称」（chat between A and B 的 B）
        #      认到就并进 user_names，后面所有过滤 / 建档 / 记忆守卫自动生效。
        try:
            _sys0 = ""
            for _m in msgs:
                if str(_m.get("role", "")).strip().lower() == "system":
                    _sys0 = _relay_message_text(_m)
                    break
            _uname = _chat_between_user_name(_sys0)
            if _uname:
                self._remember_request_user_name(_uname)
        except Exception as ex:
            self.logger.warning("[中继] 识别用户昵称失败：%s", ex)

        # ---- 0b) V5.6/V5.8：本轮的两个「按卡开关」**每轮重置**
        #      时间感知标记：'【时间感知】开/关'（没有标记 = 默认关）
        #      【演员】名单：'【演员】XXX'（没有标记 = 空，走原识别逻辑）
        #      换卡时会先重置再按新卡设置，所以不会沿用上一张卡的状态。
        self._current_card_actors = []
        try:
            self._detect_time_aware(msgs)
        except Exception as ex:
            self._current_time_aware = False
            self.logger.warning("[中继] 时间感知识别失败（按关处理）：%s", ex)

        # ---- 1) URL query ----
        try:
            q = qs or {}
            for key in RELAY_CARD_QUERY_KEYS:
                raw = q.get(key)
                if isinstance(raw, (list, tuple)):
                    raw = raw[0] if raw else None
                val = _relay_fix_text(raw).strip() if raw is not None else ""
                if val:
                    card = val
                    break
            speaker = _relay_query_char(q) or None
            # V5.8：卡已知 → 立刻应用开场白【演员】名单（建档 + 挂本卡）
            if card:
                self._apply_card_actors(msgs, card)
            if card or speaker:
                source = DETECT_SOURCE_QUERY
        except Exception as ex:
            self.logger.warning("[中继] 识别(query)失败：%s", ex)

        # ---- 2) Header ----
        if not (card or speaker):
            try:
                hdrs = headers or {}

                def _hdr(name: str) -> str:
                    for key, value in (hdrs.items() if isinstance(hdrs, dict)
                                       else []):
                        if str(key).strip().lower() == name.lower():
                            return _relay_fix_text(value).strip()
                    return ""

                cval = _hdr(RELAY_CARD_HEADER)
                chal = _hdr(RELAY_CHAR_HEADER)
                if cval or chal:
                    card = cval or None
                    speaker = chal or None
                    source = DETECT_SOURCE_HEADER
                    # V5.8：卡已知 → 立刻应用开场白【演员】名单
                    if card:
                        self._apply_card_actors(msgs, card)
            except Exception as ex:
                self.logger.warning("[中继] 识别(header)失败：%s", ex)

        # ---- 3) 本地扫描 ----
        # V5.9：这一步的门槛从「卡和说话人都没有」放宽成「还不知道说话人」——
        #       因为卡可能是 query/header/【卡名】给的，但说话人还得本地扫；
        #       所有扫名字的子步骤一律只吃 _character_candidates_for_scan()
        #       给的候选名单（【演员】 > 当前卡 > 全库），不再全库乱扫。
        _ls_ran = False
        if not speaker:
            _ls_ran = True
            # V5.10：诊断日志 —— 先把它「看到了什么」打出来，便于判断是
            #        Tavo 没发 system，还是角色卡里的标记写得不规范
            try:
                _sys_texts = [_relay_message_text(m) for m in msgs
                              if str(m.get("role", "")).strip().lower() == "system"]
                _sys_joined = " / ".join(t.strip() for t in _sys_texts if t and t.strip())
                if _sys_joined:
                    self.logger.info("[识别] 本地扫描收到的 system 消息（前200字）：%s",
                                     _sys_joined[:200])
                else:
                    self.logger.info("[识别] 本地扫描：本轮没有 system 消息（或内容为空），"
                                     "卡名/角色只能靠历史或 LLM 兜底")
            except Exception as ex:
                self.logger.warning("[识别] system 诊断日志失败：%s", ex)

            # 3-0 V5.8：开场白里明确写了【卡名】→ 本地直接采信
            #       **优先于一切猜测**（包括 assistant.name 反查、Tavo 历史残留）
            #       （库里没这张卡也行，先建卡；不再依赖 LLM 认卡）
            if not card:
                try:
                    declared = self._scan_declared_card_name(msgs)
                    if declared:
                        card = declared
                        self.logger.info("[中继] 开场白【卡名】=%r（本地声明）", card)
                        try:
                            self.card_mgr.get_or_create(card)
                        except Exception as ex:
                            self.logger.warning("[中继] 【卡名】建卡失败：%s", ex)
                        try:
                            self.remember_card_name(card)
                        except Exception:
                            pass
                        self._apply_card_actors(msgs, card)
                except Exception as ex:
                    self.logger.warning("[中继] 识别(卡名标记)失败：%s", ex)

            # 候选名单（V5.9 唯一入口：【演员】 > 当前卡 > 全库）
            cands = self._character_candidates_for_scan(card)

            # 3a. 最后一条带 name 的 assistant -> 说话人 + 反查卡
            #     V5.9：这个名字必须落在候选名单里（Tavo 历史残留的名字不算）
            try:
                nm = _relay_last_assistant_name(msgs)
                if nm:
                    if cands and nm not in cands:
                        self.logger.info(
                            "[中继] assistant.name=%r 不在候选名单 %s 里，忽略",
                            nm, cands)
                    else:
                        row = self.char_mgr.get(nm)
                        if row is not None:
                            speaker = str(row.get("name") or nm)
                            pc = self.card_mgr.card_of_character(speaker)
                            # V5.9：已有卡（query/header/【卡名】）不被反查覆盖
                            if pc and not card:
                                card = str(pc.get("name") or "")
                                # V5.8：反查出卡 → 应用【演员】名单
                                self._apply_card_actors(msgs, card)
            except Exception as ex:
                self.logger.warning("[中继] 识别(assistant_name)失败：%s", ex)

            # 3a-new：从 current_message（用户这轮说的话）里找唯一被提及的本卡角色。
            #   **排在 3a 之后，覆盖 3a 的结果** —— 3a 命中的是「上一轮的说话人」，
            #   而 current_message 命中唯一才是「这一轮的剧情焦点」。
            #   例：上一轮 assistant=甲，用户说"我去找乙" →
            #       3a 会命中甲，3a-new 用乙覆盖它。
            #   为什么排序在 3a 之后：3a 体内没有 `if not speaker` 守卫、
            #   无条件赋值 speaker，排在它前面会被覆盖。而 query/header 已声明
            #   speaker 时，外层 `if not speaker`(L13327) 会跳过整条链 → 不越权。
            #   匹配三路：全名 / 简称（去首字，仅全名≥3字）/ 别名。
            #   仅在卡已知时启用（card 为空时候选退到全库，可能命中别卡）。
            # [3a-new 前置] 卡还没识别时先扫一次 system ——
            # 3b 才会正式扫卡，但 3a-new 排在 3b 之前，卡会是空的。
            if not card:
                try:
                    _sc = self._scan_system_prompt_for_card(msgs)
                    if _sc:
                        card = _sc
                        # 3b 的 if not card: 会被这次前置扫卡跳过 ——
                        # 把 3b 里那两件事先做了，否则【演员】名单不生效、cands 不刷新
                        try:
                            self._apply_card_actors(msgs, card)
                        except Exception as _ex1:
                            self.logger.warning(
                                "[中继] 3a-new 前置应用【演员】失败：%s", _ex1)
                        try:
                            cands = self._character_candidates_for_scan(card, only_active=True)
                        except Exception as _ex2:
                            self.logger.warning(
                                "[中继] 3a-new 前置刷新候选失败：%s", _ex2)
                        self.logger.info("[中继] 3a-new 前置扫卡：%r", card)
                except Exception as ex:
                    self.logger.warning("[中继] 3a-new 前置扫卡失败：%s", ex)
            # [诊断] 临时日志，查完删
            try:
                _diag_cmsg = _relay_last_user_message(msgs) if msgs else ""
                try:
                    _ex = extract_real_user_text(_diag_cmsg)
                    if _ex.get("status") == "success" and _ex.get("text"):
                        _diag_cmsg = _ex["text"]
                except Exception:
                    pass
                _diag_cands = []
                try:
                    _diag_cands = list(self._character_candidates_for_scan(card))[:8]
                except Exception:
                    pass
                self.logger.info(
                    "[3a-new诊断] card=%r cmsg_len=%d cmsg_head=%r cands=%s",
                    card, len(_diag_cmsg), _diag_cmsg[:60], _diag_cands)
            except Exception as ex:
                self.logger.warning("[3a-new诊断] 失败：%s", ex)
            if card:
                try:
                    _cmsg = _relay_last_user_message(msgs)
                    try:
                        _ex = extract_real_user_text(_cmsg)
                        if _ex.get("status") == "success" and _ex.get("text"):
                            _cmsg = _ex["text"]
                    except Exception:
                        pass
                    _cands = self._character_candidates_for_scan(card)
                    _cands_active = self._character_candidates_for_scan(card, only_active=True)
                    # 【10-04 补丁】3a-obj：说话对象标记通道
                    #   对着XX说/对XX说/跟XX说/和XX说/向XX说/告诉XX
                    _obj_hit_ok = False
                    if _cmsg and _cands:
                        _obj_hits = []
                        for _n in _cands:
                            if self._should_skip_character(_n, card):
                                continue
                            if re.search(
                                    r"(?<!不)(?<!没)(?<!别)(?:对着|对|跟|和|向|告诉)\s*"
                                    + re.escape(_n)
                                    + r"\s*(?:说|道|问|答|喊|叫)",
                                    _cmsg):
                                _obj_hits.append(_n)
                        if len(_obj_hits) == 1:
                            speaker = _obj_hits[0]
                            _obj_hit_ok = True
                            self.logger.info(
                                "[中继] 识别(3a-obj)：说话对象标记命中 %r",
                                speaker)
                        elif len(_obj_hits) > 1:
                            self.logger.info(
                                "[中继] 识别(3a-obj)：说话对象标记命中多个 %s，不猜",
                                _obj_hits)
                    if (not _obj_hit_ok) and _cmsg and _cands:
                        _hits = []
                        _hit_cids: set = set()  # [10-06] 同一角色多名字去重
                        for _n in _cands:
                            if self._should_skip_character(_n, card):
                                continue
                            _matched = False
                            # 全名 —— 必须在呼语位置（开头 + 称呼符）
                            if _n in _cmsg and self._name_in_vocative_position(_cmsg, _n):
                                _matched = True
                            # 简称（去首字）
                            elif len(_n) >= 3 and _n[1:] in _cmsg \
                                    and self._name_in_vocative_position(_cmsg, _n[1:]):
                                _matched = True
                            # 别名
                            else:
                                _row = self.char_mgr.get(_n)
                                if _row:
                                    for _a in _as_list(_row.get("aliases")):
                                        _sa = str(_a).strip()
                                        if _sa and _sa != _n and _sa in _cmsg \
                                                and self._name_in_vocative_position(_cmsg, _sa):
                                            _matched = True
                                            break
                            if _matched:
                                # [10-06] 同一角色多个名字（全名+别名）去重；真多角色仍不猜
                                _cid_n = None
                                try:
                                    _cid_n = self.char_mgr.resolve_id(_n)
                                except Exception:
                                    _cid_n = None
                                if _cid_n is not None:
                                    if _cid_n in _hit_cids:
                                        continue
                                    _hit_cids.add(_cid_n)
                                _hits.append(_n)
                        # 【10-04 补丁】唯一角色兜底：_hits 为空但
                        #   cmsg 里恰好 1 个本卡角色 → 用它
                        if not _hits:
                            _all_in_cmsg = [
                                _n for _n in _cands_active
                                if not self._should_skip_character(_n, card)
                                and _n in _cmsg
                            ]
                            if len(_all_in_cmsg) == 1:
                                _hits = _all_in_cmsg
                                self.logger.info(
                                    "[中继] 识别(3a-new)：cmsg 唯一角色 %r，"
                                    "作为本轮说话人", _hits[0])
                        if len(_hits) == 1:
                            speaker = _hits[0]
                            self.logger.info(
                                "[中继] 识别(3a-new)：current_message 命中唯一角色 %r，"
                                "作为本轮说话人", speaker)
                        elif len(_hits) > 1:
                            _multi_hit_round = True
                            self.logger.warning(
                                "[中继] 识别(3a-new)：current_message 命中多个 %s，不猜 → 交下游兜底",
                                _hits)
                except Exception as ex:
                    self.logger.warning(
                        "[中继] 识别(3a-new)失败（继续原逻辑）：%s", ex)

            # 3a-keep：本轮还没识别出说话人 → 沿用上一轮暂存的说话人。
            #   原因：Tavo 的 assistant 消息不带 name 字段，3a 拿不到东西；
            #   3a-new 只在用户消息明确提角色时命中；都没命中时，3b 会
            #   fallback 到 main_character，导致说话人无理由跳回"默认角色"。
            #   读 conversation_meta 的 pending_character（上一轮暂存）。
            if not speaker and card:
                try:
                    _prev_sp = str(
                        self.db.get_meta("pending_character") or "").strip()
                    if _prev_sp and self._should_skip_character(_prev_sp, card):
                        self.logger.info(
                            "[中继] 识别(3a-keep)：旧 speaker=%r 属于别卡，跳过（防跨卡）",
                            _prev_sp)
                    if _prev_sp and not self._should_skip_character(_prev_sp, card):
                        _cands_now = cands or []
                        _in_card = False
                        if _cands_now:
                            _in_card = _prev_sp in _cands_now
                        else:
                            try:
                                _in_card = _prev_sp in self._card_character_names(card)
                            except Exception:
                                _in_card = False
                        if _in_card:
                            # 【10-04 补丁】守卫：本轮 cmsg 里出现
                            #   其他本卡角色，且旧 speaker 自己没被
                            #   提到 → 不沿用
                            _other_in_cmsg = False
                            _cmsg_k = ""
                            try:
                                _cmsg_k = _relay_last_user_message(msgs) or ""
                                if _cmsg_k:
                                    try:
                                        _ex_k = extract_real_user_text(_cmsg_k)
                                        if _ex_k.get("status") == "success" and _ex_k.get("text"):
                                            _cmsg_k = _ex_k["text"]
                                    except Exception:
                                        pass
                            except Exception:
                                _cmsg_k = ""
                            if _cmsg_k:
                                for _n in (_cands_now or []):
                                    if _n != _prev_sp and _n in _cmsg_k:
                                        _other_in_cmsg = True
                                        break
                            if _other_in_cmsg and _prev_sp not in _cmsg_k:
                                self.logger.info(
                                    "[中继] 3a-keep：本轮出现其他角色，不沿用 %r",
                                    _prev_sp)
                            else:
                                speaker = _prev_sp
                                if source == DETECT_SOURCE_NONE:
                                    source = DETECT_SOURCE_LOCAL_SCAN
                                self.logger.info(
                                    "[中继] 3a-keep：沿用上一轮说话人 %r", _prev_sp)
                except Exception as ex:
                    self.logger.warning("[中继] 3a-keep 失败：%s", ex)

            # 3b. system 扫已知卡名 -> 卡；再扫角色名 -> 说话人（须属于该卡）
            #     （【卡名】标记已在 3-0 处理过；这里只兜"库里已有的卡名"）
            if not card:
                try:
                    card = self._scan_system_prompt_for_card(msgs) or None
                    # V5.8：卡是从 system 扫出来的 → 应用【演员】名单
                    if card:
                        self._apply_card_actors(msgs, card)
                        cands = self._character_candidates_for_scan(card)
                except Exception as ex:
                    self.logger.warning("[中继] 识别(card_scan)失败：%s", ex)
            if not speaker and card:
                try:
                    cand = self._scan_system_prompt_known_names(
                        msgs, names=cands or None, card=card)
                    if cand:
                        in_card = self._card_character_names(card)
                        if not in_card or cand in in_card:
                            speaker = cand
                    if not speaker:
                        # V5.9：卡的 main_character 也必须在候选名单里
                        mc = self._card_main_character(card)
                        if mc and (not cands or mc in cands):
                            speaker = mc
                        elif mc:
                            self.logger.info(
                                "[中继] 卡的 main_character %r 不在候选名单 %s 里，"
                                "不用", mc, cands)
                except Exception as ex:
                    self.logger.warning("[中继] 识别(card_speaker)失败：%s", ex)

            # 3c. 沿用 system prompt 抠名字 -> 说话人 -> 反查卡
            #     V5.9：抠出来的名字必须在候选名单里（【演员】/卡下角色），
            #           否则丢掉（Tavo 历史里别的卡的角色不算）
            if not speaker:
                try:
                    # V5.9：候选名单为空、而卡/演员已经有了 → 不猜（别把别卡角色拉进来）
                    if cands or not (card or self._current_card_actors):
                        cand = self._scan_system_prompt_for_character(msgs)
                    else:
                        cand = None
                    if cand and cands and cand not in cands:
                        self.logger.info(
                            "[中继] system 扫描挑出 %r 不在候选名单 %s 里，丢弃",
                            cand, cands)
                        cand = None
                    if cand:
                        row = self.char_mgr.get(cand)
                        if row is not None:
                            speaker = str(row.get("name") or cand)
                            pc = self.card_mgr.card_of_character(speaker)
                            if pc and not card:
                                card = str(pc.get("name") or "")
                except Exception as ex:
                    self.logger.warning("[中继] 识别(system_prompt)失败：%s", ex)

            # 3d. 最后回到 messages 正文扫描（content_scan）
            #     V5.9：候选名单统一由 _character_candidates_for_scan() 给，
            #           不再全库扫（【演员】 > 当前卡 > 全库）
            if not speaker:
                try:
                    cand = self._scan_messages_for_character(msgs, card)
                    if cand:
                        speaker = cand
                except Exception as ex:
                    self.logger.warning("[中继] 识别(content_scan)失败：%s", ex)

            # V5.9：别把 query/header 已定的来源覆盖掉
            if (card or speaker) and source == DETECT_SOURCE_NONE:
                source = DETECT_SOURCE_LOCAL_SCAN

        # ---- 3e) V5.8：【演员】名单里刚好只有一个 → 直接就是说话人 ----
        #      本地就能定，不烧 token、也不受 LLM 抽风影响。
        #      （显式 ?char= / Header / assistant.name / 本地扫描 命中的优先，不用这条）
        if not speaker and self._current_card_actors:
            try:
                _acts = [n for n in self._current_card_actors
                         if not self._should_skip_character(n, card)]
            except Exception:
                _acts = []
            if len(_acts) == 1:
                speaker = _acts[0]
                if source == DETECT_SOURCE_NONE:
                    source = DETECT_SOURCE_LOCAL_SCAN
                self.logger.info(
                    "[中继] 开场白【演员】只有一个 %r，直接当说话人", speaker)

        if _multi_hit_round and speaker:
            self.logger.warning(
                "[识别] 多命中兜底：最终 speaker=%r（来源=%s）",
                speaker, source)
        elif _multi_hit_round:
            self.logger.warning(
                "[识别] 多命中兜底：最终 speaker=None（无兜底）")
        # V5.10：本地扫描结果（认没认出来都打，便于对照上面的 system 原文）
        if _ls_ran:
            self.logger.info("[识别] 本地扫描结果：card=%s speaker=%s",
                             card or "（无）", speaker or "（无）")

        # ---- 3f) [V2.3 别名映射] 本地扫描认不出来时，先查「别名」再谈兜底 ----
        # 典型场景：UI 里建卡「山田家」(别名「家庭」)、角色「山田一郎」(别名「爸爸」)，
        # 而 Tavo 只发来「家庭 / 爸爸」——真名对不上，但别名能命中。命中即视为
        # 当前上下文：**不烧 token、也不掉进 default 兜底**。
        # [V2.6] 把本轮解析出的玩家名单按卡落库：异步回写（后台线程）和下一轮
        # 请求即使拿不到 msgs，也能靠 conversation_meta 判定谁是用户。
        if card and getattr(self, "_request_user_names", None):
            try:
                self.db.set_meta("card_user_names:" + str(card),
                                 json.dumps(self._request_user_names,
                                            ensure_ascii=False))
            except Exception as ex:
                self.logger.warning("[识别] 落库动态玩家名单失败：%s", ex)

        if card or speaker:
            try:
                _mc, _ms = self._alias_resolve(card, speaker)
                if _mc and _mc != card:
                    self.logger.info("[识别] 别名映射成功：%s -> %s", card, _mc)
                    card = _mc
                if _ms and _ms != speaker:
                    self.logger.info("[识别] 别名映射成功：%s -> %s", speaker, _ms)
                    speaker = _ms
                if _ms:
                    self.remember_card_name(card or "")
                if _mc or _ms:
                    if source == DETECT_SOURCE_NONE:
                        source = DETECT_SOURCE_LOCAL_SCAN
            except Exception as ex:
                self.logger.warning("[识别] 别名映射失败：%s", ex)

        # ---- 3g) [V2.5 卡牌强制主角] 卡已定 → 说话人强制锁定为这张卡的主角 ----
        # 开启后**不再理会 Tavo 传来的任何称呼**（爸爸/哥哥/乱码都一样）：
        # 只要这张卡绑定了 main_character，说话人就是它。
        # 卡下没有绑定主角色 → 什么都不做，退回上面的别名映射结果。
        if card and getattr(self.config.memory,
                            "enforce_card_main_character", False):
            try:
                _main = self._card_main_character(card, strict=True)
                if _main:
                    if speaker and speaker != _main:
                        self.logger.info(
                            "[识别] 强制接管：卡片「%s」已锁定主角色「%s」，"
                            "忽略 Tavo 传入的 %s", card, _main, speaker)
                    else:
                        self.logger.info(
                            "[识别] 强制接管：卡片「%s」已锁定主角色「%s」",
                            card, _main)
                    speaker = _main
                    if source == DETECT_SOURCE_NONE:
                        source = DETECT_SOURCE_LOCAL_SCAN
                elif speaker:
                    self.logger.warning(
                        "[识别] 强制接管跳过：卡片「%s」没有绑定 main_character，"
                        "仍按别名映射/原逻辑取 %s", card, speaker)
            except Exception as ex:
                self.logger.warning("[识别] 强制接管失败：%s", ex)

        if source == DETECT_SOURCE_LOCAL_SCAN:
            self.logger.info("[中继] 本地扫描: card=%s speaker=%s source=%s",
                             card, speaker, source)

        # ---- 4) LLM 兜底 ----
        if not (card and speaker):
            try:
                auto = bool(getattr(self.config.llm, "auto_detect_card", True))
                if auto and self.llm is not None \
                        and getattr(self.llm, "enabled", False):
                    res = self._llm_detect_card(msgs)
                    if res:
                        applied = self._apply_llm_detection(res)
                        card = card or applied.get("card")
                        # V5.1：本地扫描挑出的 speaker 若是「用户 / 卡名」（比如
                        # 「明」），别让它用 ``speaker or ...`` 把 LLM 兜底给的
                        # 那个干净说话人挡掉 —— 换成 LLM 兜底的。
                        _ap_spk = applied.get("speaker")
                        if _ap_spk and (not speaker
                                        or self._should_skip_character(speaker,
                                                                        card)):
                            if speaker:
                                self.logger.info(
                                    "[中继] LLM 兜底：speaker=%r 命中用户/卡名"
                                    "过滤，改用 %r", speaker, _ap_spk)
                                speaker = _ap_spk
                            else:
                                speaker = _ap_spk
                        elif not speaker:
                            speaker = _ap_spk or None
                        self.logger.info(
                            "[中继] LLM 兜底: card=%s speaker=%s chars=%s",
                            applied.get("card"), applied.get("speaker"),
                            [c["name"] for c in (applied.get("characters") or [])])
                        if card or speaker:
                            source = DETECT_SOURCE_LLM
            except Exception as ex:
                self.logger.warning("[中继] LLM 兜底异常（已忽略）：%s", ex)

        # ---- 4.5) 老兜底（保住 V2 能力）：LLM 不可用时仍能从「你是X」建档 ----
        # 只有在 LLM 这条路没走通（未启用 / 返回空 / auto_detect_card=false）
        # 且系统提示词里明确写了「你是X / 扮演X / 你的名字是X」时才生效。
        if not speaker:
            try:
                cand = self._scan_system_prompt_for_character(msgs)
                if cand and len(cand) <= NAME_MAX_LEN:
                    row = _relay_get_or_create(self, cand, self.logger)
                    if row is not None:
                        speaker = str(row.get("name") or cand)
                        if card:
                            self.card_mgr.attach_character(card, speaker)
                        else:
                            pc = self.card_mgr.card_of_character(speaker)
                            if pc:
                                card = str(pc.get("name") or "")
                        self.logger.info(
                            "[中继] 本地兜底: card=%s speaker=%s source=%s",
                            card, speaker, DETECT_SOURCE_LOCAL_SCAN)
                        source = DETECT_SOURCE_LOCAL_SCAN
            except Exception as ex:
                self.logger.warning("[中继] 本地兜底(抠名字)失败：%s", ex)

        # ---- 5) 配置兜底 ----
        if not (card and speaker):
            try:
                dcard = str(getattr(self.config.llm, "default_card", "")
                            or "").strip()
                if dcard and not card:
                    if self.card_mgr.get_or_create(dcard):
                        card = dcard
                        self.remember_card_name(dcard)
                    if not speaker:
                        speaker = self._card_main_character(card)
                if not speaker:
                    dchar = str(getattr(self.config.llm, "default_character", "")
                                or "").strip()
                    if dchar:
                        row = _relay_get_or_create(self, dchar, self.logger)
                        if row is not None:
                            speaker = str(row.get("name") or dchar)
                            if card:
                                self.card_mgr.attach_character(card, speaker)
                if card or speaker:
                    source = DETECT_SOURCE_DEFAULT
            except Exception as ex:
                self.logger.warning("[中继] 识别(default)失败：%s", ex)

        # ---- 6) 活跃角色兜底 ----
        if not speaker:
            try:
                info = self.resolve_active() or {}
                for cid in list(info.get("active") or []):
                    row = self.char_mgr.get(cid)
                    if row is not None and not bool(row.get("is_user")):
                        speaker = str(row.get("name") or "")
                        pc = self.card_mgr.card_of_character(speaker)
                        if pc and not card:
                            card = str(pc.get("name") or "")
                        source = DETECT_SOURCE_RESOLVE_ACTIVE
                        break
            except Exception as ex:
                self.logger.warning("[中继] resolve_active() 兜底失败：%s", ex)

        # V3：记下本次请求的卡名 —— 后面判"该不该作为角色"（卡名不是角色）
        #     以及逐条 message 判归属时都要用。
        self._current_card = str(card or "")

        # ---- 汇总 characters（卡下角色；没有卡时给个空表）----
        chars: List[Dict[str, Any]] = []
        if card:
            try:
                chars = [{"name": r.get("name"), "role_type": r.get("role_type")}
                         for r in self.card_mgr.list_characters(card)]
            except Exception as ex:
                self.logger.warning("[中继] 汇总卡下角色失败：%s", ex)
        if not chars and speaker:
            row = self.char_mgr.get(speaker)
            if row is not None:
                chars = [{"name": row.get("name"),
                          "role_type": row.get("role_type")}]

        # ---- 6.5) V5.1：speaker 也要过「用户 / 卡名」这一道过滤 ----
        #   Tavo 的「用户身份」（如「明」）跟卡名一样，**绝不是 AI 扮演的角色**：
        #   命中就改从当前卡的角色列表里挑（main_character 优先，其次 chars[0]），
        #   挑不到就把 speaker 置 None —— 宁可「没识别出说话人」（不注入、不落库），
        #   也不能把用户当说话人写进记忆。
        if speaker and self._should_skip_character(speaker):
            self.logger.info("[中继] speaker=%r 命中用户/卡名过滤，从 chars 改选",
                             speaker)
            picked = self._reselect_speaker(card, chars)
            speaker = picked or None
            if speaker:
                if all(str(c.get("name") or "") != speaker for c in chars):
                    _srow = self.char_mgr.get(speaker)
                    chars.append({"name": speaker,
                                  "role_type": (_srow or {}).get("role_type")})
                self.logger.info("[中继] speaker 改选为 %r（来源=%s）",
                                 speaker, source)
            else:
                self.logger.info("[中继] speaker 改选失败（卡下没有可用角色），"
                                 "置 None —— 本轮不注入记忆、不落库")

        # ---- 6.6) [跨卡修复] speaker 必须真的属于本卡 ----
        # 兜底链末端的 resolve_active / local_scan 拿到的是**全局**线索，
        # 跟本卡的阵容无关，落到别的卡的角色的情况实测出现过：
        #   card=软萌无敌可爱的女儿 却识别出 speaker=甲（来源 resolve_active），
        #   之后 local_scan 又从历史里那条**已标错**的 assistant 扫出同一个名字，
        #   错误自我延续 → 回复被记到甲名下 → 建档时又把她挂到了这张卡下。
        # 这里做最后一道闸：卡里没有这个名字 → speaker 置 None
        #（本轮不注入、不落库），宁可漏识别，也不跨卡串味。
        if speaker and card:
            try:
                known = {str(c.get("name") or "").strip()
                         for c in (chars or []) if c}
                known.discard("")
                bad = False
                if known:
                    bad = str(speaker).strip() not in known
                else:
                    # 本卡还没有任何角色：用「这个名字是不是已属于别的卡」兜一层
                    _pc = self.card_mgr.card_of_character(speaker)
                    _pcn = str((_pc or {}).get("name") or "").strip()
                    bad = bool(_pcn) and _pcn != str(card)
                if bad:
                    self.logger.warning(
                        "[中继] 跨卡拦截：speaker=%r 不属于卡 %r（来源=%s），"
                        "置 None —— 本轮不注入记忆、不落库",
                        speaker, card, source)
                    speaker = None
            except Exception as ex:
                self.logger.warning("[中继] speaker 跨卡校验失败（跳过校验）：%s", ex)

        out = {"card": card or None, "speaker": speaker or None,
               "characters": chars,
               "source": source if (card or speaker) else DETECT_SOURCE_NONE}
        self.last_card_detect = dict(out)
        return out

    # ------------------------------------------------------------------
    # V3 追加：每条 message 独立判归属（记忆永远挂角色，绝不挂卡）
    # ------------------------------------------------------------------
    def _ensure_character_in_card(
        self,
        name: Any,
        card_ref: Any = None,
    ) -> Optional[str]:
        """取角色（没有就建），并确保它挂在该卡下；返回规范角色名。"""
        nm = _relay_fix_text(name).strip()
        if not nm:
            return None
        # [用户修复] 用户身份必须在 **建档之前** 判定。老代码先 get_or_create
        # 再判 _is_user_name，于是「用户」这种常见称呼会被先建出一行
        # is_user=0 的幻影角色（char 4 就是这么来的），既污染卡片角色列表，
        # 又在它名下攒下一批无人认领的记忆。
        if self._is_user_name(nm):
            existing = self.char_mgr.get(nm)
            if existing is None:
                self.logger.warning(
                    "[中继] 归属：%r 命中「用户」身份（user_names / is_user）"
                    "且库中无此角色，跳过建档", nm)
                return None
            self.logger.warning(
                "[中继] 归属：%r 命中「用户」身份（已有 id=%s），跳过建档与挂卡",
                nm, existing.get("character_id"))
            self.remember_character_name(str(existing.get("name") or nm))
            return str(existing.get("name") or nm)
        try:
            row = self.char_mgr.get(nm)
            if row is None:
                row = self.char_mgr.get_or_create(nm)
            if row is None:
                return None
            real = str(row.get("name") or nm)
            self.remember_character_name(real)
            # V3：用户（is_user=1 或在 user_names 里，比如「明」）不挂卡 ——
            # 用户不属于任何卡的「角色阵容」，也不建记忆。
            if card_ref and not self._is_user_name(real):
                card_id = self.card_mgr._resolve_card_id(card_ref)
                cur_id = _to_int(row.get("card_id"))
                if card_id is not None and cur_id != card_id:
                    if cur_id is None:
                        # 还没挂过卡 → 正常挂上
                        self.card_mgr.attach_character(card_id, real)
                    else:
                        # [跨卡修复] 已属于**别的卡**：不再悄悄搬过来。
                        # 老代码在这里无条件 attach，等于「谁来报这个名字，
                        # 角色就跟谁走」—— 实测甲因此被移植到了另一张卡下。
                        self.logger.warning(
                            "[中继] 跨卡拦截：角色 %r 已属于别的卡"
                            "（card_id=%s），不挂到 %r；如确需改卡请手动处理",
                            real, cur_id, card_ref)
            return real
        except Exception as ex:
            self.logger.warning("[中继] 归属：建档 %r 失败：%s", name, ex)
            return None

    @staticmethod
    def _marker_name_of(line: Any, names: Sequence[str]) -> Optional[str]:
        """一行是不是「角色标记行」——是就返回那个角色名。

        只认「去掉前缀表情/符号后，整行就是某个卡下角色名」的情况：
            💗 甲   /   ❤️乙   /   【丙】   /   丁
        认不出返回 None（`💔 心声`、`📍 位置` 这类无名字的标记都不认）。
        """
        s = str(line or "").strip()
        if not s or len(s) > 60:
            return None
        i = 0
        while i < len(s) and not s[i].isalnum():
            i += 1
        core = s[i:].strip()
        if not core:
            return None
        for nm in names or ():
            if not nm:
                continue
            if core == nm:
                return nm
            # [放宽] 「名字 + 分隔符 + 描述」也算标记行（👤 己 | 16岁，高中生…）。
            #        只认行首（前缀符号已剥掉），绝不做行内任意位置的子串匹配。
            if (core.startswith(nm)
                    and core[len(nm):len(nm) + 1] in MARKER_NAME_SEPARATORS):
                return nm
        return None

    def _split_assistant_segments(
        self, text: Any, card_ref: Any = None,
    ) -> List[Tuple[Optional[str], str]]:
        """按回复里的**角色标记**把 assistant 文本拆成多段。

        返回 ``[(角色名 或 None, 段文本), ...]``：
        * 名字非 None = 该段的标记直接点名，调用方**不得再推断**
        * 名字为 None = 没标记的开头段（正文）

        找不到任何标记 → 返回 ``[(None, 全文)]``，调用方保持原行为。

        ★ 状态栏截断：出现以 💗/❤️/💔 开头的行时，从该行起整块丢弃。
        这些是角色的瞬时内心/位置/行为（状态栏），不是对话内容，不该进记忆。
        """
        t = str(text or "")
        if not t.strip():
            return [(None, t)]
        # ★ 状态栏截断：正文与状态栏的分界点是第一个状态栏标记行
        _SB_MARKERS = ("💗", "❤️", "💔")
        lines = t.split("\n")
        cut_idx = None
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s and s.startswith(_SB_MARKERS):
                cut_idx = i
                break
        if cut_idx is not None:
            body_part = "\n".join(lines[:cut_idx]).strip()
            if body_part:
                t = body_part
        if not t.strip():
            return [(None, t)]
        try:
            names = self._card_character_names(card_ref)
        except Exception:
            names = []
        if not names:
            return [(None, t.strip())]
        segs: List[Tuple[Optional[str], str]] = []
        cur_name: Optional[str] = None
        cur: List[str] = []
        found = False
        for ln in t.split("\n"):
            cand = self._marker_name_of(ln, names)
            if cand:
                found = True
                body = "\n".join(cur).strip()
                if body or cur_name is not None:
                    segs.append((cur_name, body))
                cur_name = cand
                cur = []
            else:
                cur.append(ln)
        segs.append((cur_name, "\n".join(cur).strip()))
        segs = [(n, s) for (n, s) in segs if s]
        if not found or not segs:
            return [(None, t.strip())]
        return segs

    def _extract_scene_from_assistant(self, text: Any) -> Dict[str, Dict[str, str]]:
        """从 assistant 输出里抽 📍 位置 / 🎭 行为 两段。

        格式约定（写在卡里，模型输出）：
            📍 位置
            甲：某宅·偏房
            乙：某宅·内室

            🎭 行为
            甲：坐在床沿，手指捻着布带

        返回：
            {"locations": {"甲": "某宅·偏房", ...},
             "actions":   {"甲": "坐在床沿...", ...}}
        找不到返回 {"locations": {}, "actions": {}}。
        任何一行不符合"角色名：内容"格式 → 跳过该行，不报错。
        """
        import re as _re
        result: Dict[str, Dict[str, str]] = {"locations": {}, "actions": {}}
        t = str(text or "")
        if not t:
            return result
        section = None
        for ln in t.split("\n"):
            s = ln.strip()
            if not s:
                continue
            if s.startswith("📍"):
                section = "loc"
                continue
            if s.startswith("🎭"):
                section = "act"
                continue
            if s.startswith(("💗", "❤️", "💔")):
                section = None
                continue
            if s.startswith("━"):
                section = None
                continue
            if section is None:
                continue
            m = _re.match(r"^([^：:\s][^：:]{0,20})[：:](.+)$", s)
            if not m:
                continue
            name = m.group(1).strip()
            val = m.group(2).strip()
            if not name or not val:
                continue
            if section == "loc":
                result["locations"][name] = val
            elif section == "act":
                result["actions"][name] = val
        return result

    def _save_scene_state(self, card_name: str,
                          scene: Dict[str, Dict[str, str]]) -> None:
        """把场景状态写进 conversation_meta。键名：scene_state:<card_name>，值：JSON。"""
        import json as _json
        if not card_name:
            return
        if not scene or (not scene.get("locations") and not scene.get("actions")):
            return
        key = "scene_state:%s" % str(card_name)
        try:
            value = _json.dumps(scene, ensure_ascii=False)
            self.db.set_meta(key, value)
        except Exception as ex:
            self.logger.warning("[场景] 保存失败：%s", ex)

    def _load_scene_state(self, card_name: str) -> Dict[str, Dict[str, str]]:
        """读场景状态。没有/解析失败 → 返回空 dict。"""
        import json as _json
        empty = {"locations": {}, "actions": {}}
        if not card_name:
            return empty
        key = "scene_state:%s" % str(card_name)
        try:
            raw = self.db.get_meta(key)
            if not raw:
                return empty
            data = _json.loads(raw)
            if not isinstance(data, dict):
                return empty
            return {
                "locations": dict(data.get("locations") or {}),
                "actions": dict(data.get("actions") or {}),
            }
        except Exception as ex:
            self.logger.warning("[场景] 读取失败：%s", ex)
            return empty

    def _parse_story_time(self, text: Any, prev: str = "") -> str:
        """从文本里解析剧情时间戳，返回新的 story_time 字符串（或空串=不更新）。

        规则见任务说明。text 优先扫前 30 字，兜底扫全文。
        时段词表固定；日期"X月X日"；钟点"X点[X分|半]"。
        """
        import re as _re
        if not text:
            return ""
        t = str(text)
        _hour = r"[一二三四五六七八九十百零两]+点(?:[一二三四五六七八九十百零两半]+分?)?(?!刻)"
        _period = r"(?:清晨|早晨|早上|上午|中午|正午|晌午|下午|黄昏|傍晚|晚上|夜晚|半夜|深夜|凌晨)"
        _date = r"[一二三四五六七八九十]+月[一二三四五六七八九十]+日?"
        # 三种模式，按优先级
        _full = _re.compile(r"(" + _date + r")[\s，,、:：]*(" + _period + r")\s*(" + _hour + r")?")
        _no_date = _re.compile(r"(" + _period + r")\s*(" + _hour + r")")
        _date_only = _re.compile(r"(" + _date + r")")
        scan = t[:30]
        # 1) 完整时间戳
        hits_full = list(_full.finditer(scan)) or list(_full.finditer(t))
        if hits_full:
            m = hits_full[-1]
            d, p, h = m.group(1), m.group(2), (m.group(3) or "")
            return "%s%s%s" % (d, p, h)
        # 2) 时段+钟点（日期继承）
        hits_nd = list(_no_date.finditer(scan)) or list(_no_date.finditer(t))
        if hits_nd:
            m = hits_nd[-1]
            p, h = m.group(1), m.group(2)
            prev_date = ""
            if prev:
                _md = _date_only.search(str(prev))
                if _md:
                    prev_date = _md.group(1)
            if prev_date:
                return "%s%s%s" % (prev_date, p, h)
            # 没有日期可继承 → 只记时段+钟点（冷启动解死锁）
            return "%s%s" % (p, h)
        # 3) 只有日期（没时段）→ 不更新（用户约定：写日期必写时段）
        return ""

    def _update_story_time(self, user_text: str, card: Any = None) -> str:
        """读 conversation_meta 的 story_time → 解析 → 更新 → 返回新值。"""
        key = "story_time:" + str(card or self._current_card or "")
        if key == "story_time:":
            self.logger.warning("[时间] 没有卡名，本轮不更新 story_time")
            return ""
        try:
            prev = str(self.db.get_meta(key) or "")
        except Exception:
            prev = ""
        try:
            new = self._parse_story_time(user_text, prev=prev)
        except Exception as ex:
            self.logger.warning("[时间] 解析失败：%s", ex)
            return prev
        if new and new != prev:
            try:
                self.db.set_meta(key, new)
                self.logger.info("[时间] 更新 story_time: %r -> %r", prev, new)
            except Exception as ex:
                self.logger.warning("[时间] 保存失败：%s", ex)
            return new
        return prev

    def _user_mentioned_names(self, user_text: str, card_ref: Any) -> set:
        """扫用户消息，找出被提到的本卡角色名。

        这些角色本轮"允许自由更新位置"（用户是导演）。
        """
        t = str(user_text or "")
        if not t:
            return set()
        try:
            names = self._card_character_names(card_ref)
        except Exception:
            return set()
        mentioned = set()
        for nm in names or ():
            if nm and nm in t:
                mentioned.add(nm)
        return mentioned

    def _has_movement_evidence(self, text: Any, name: str) -> bool:
        """检查正文里有没有"角色名 + 移动词"的组合。

        只在状态栏之前的正文部分检查。
        角色名后 8 字内出现任一移动词 → 算有依据。
        """
        t = str(text or "")
        if not t or not name:
            return False
        _sb = ("💗", "❤️", "💔")
        lines = t.split("\n")
        body_lines = []
        for ln in lines:
            s = ln.strip()
            if s and s.startswith(_sb):
                break
            body_lines.append(ln)
        body = "\n".join(body_lines)
        if not body:
            return False
        idx = 0
        while True:
            pos = body.find(name, idx)
            if pos < 0:
                break
            tail = body[pos + len(name):pos + len(name) + 8]
            for w in _SCENE_MOVE_WORDS:
                if w in tail:
                    return True
            idx = pos + len(name)
        return False

    def _same_region(self, loc_a: str, loc_b: str) -> bool:
        """两个位置是否同区：任一级段完全同名，或一方为另一方子串（≥2 字）。"""
        if not loc_a or not loc_b:
            return False
        sa = [s.strip() for s in str(loc_a).split("·") if s.strip()]
        sb = [s.strip() for s in str(loc_b).split("·") if s.strip()]
        if not sa or not sb:
            return False
        for x in sa:
            for y in sb:
                if x == y:
                    return True
                if len(x) >= 2 and len(y) >= 2 and (x in y or y in x):
                    try:
                        self.logger.info(
                            "[场景] 子串匹配放行: %r ↔ %r", loc_a, loc_b)
                    except Exception:
                        pass
                    return True
        return False

    def _merge_scene(self, old_scene: Dict, new_scene: Dict,
                     assistant_text: str, exempt_names: set
                     ) -> Tuple[Dict, Dict]:
        """仲裁：新位置跟旧位置比对，有依据才更新。

        返回 (merged_scene, stats)。stats = {updated, blocked}。
        """
        stats = {"updated": 0, "blocked": 0}
        old_locs = dict((old_scene or {}).get("locations") or {})
        old_acts = dict((old_scene or {}).get("actions") or {})
        new_locs = dict((new_scene or {}).get("locations") or {})
        new_acts = dict((new_scene or {}).get("actions") or {})

        merged_locs: Dict[str, str] = {}
        merged_acts: Dict[str, str] = {}

        all_names = set(old_locs) | set(new_locs)
        for nm in all_names:
            if not nm:
                continue
            old_loc = old_locs.get(nm)
            new_loc = new_locs.get(nm)
            if not new_loc:
                if old_loc:
                    merged_locs[nm] = old_loc
                if nm in old_acts:
                    merged_acts[nm] = old_acts[nm]
                continue
            if not old_loc or new_loc == old_loc:
                merged_locs[nm] = new_loc
                if nm in new_acts:
                    merged_acts[nm] = new_acts[nm]
                elif nm in old_acts:
                    merged_acts[nm] = old_acts[nm]
                if new_loc != old_loc:
                    stats["updated"] += 1
                continue
            has_evidence = (nm in exempt_names) or \
                self._has_movement_evidence(assistant_text, nm) or \
                self._same_region(old_loc, new_loc)
            if has_evidence:
                merged_locs[nm] = new_loc
                if nm in new_acts:
                    merged_acts[nm] = new_acts[nm]
                stats["updated"] += 1
            else:
                merged_locs[nm] = old_loc
                if nm in old_acts:
                    merged_acts[nm] = old_acts[nm]
                self.logger.info(
                    "[场景] 拦截 name=%s 旧=%s 新=%s",
                    nm, old_loc, new_loc)
                stats["blocked"] += 1

        return {"locations": merged_locs, "actions": merged_acts}, stats

    @staticmethod
    def _speaker_position_score(text: Any, name: str) -> int:
        """「名字在正文里的说话人证据强度」（V3.1 归属收紧用）。

        3 = 出现在正文开头（可隔装饰符），且后面不是呼语标点 → 像主语/说话人
        1 = 出现在正文开头但紧跟呼语标点（，！？） → 是在喊对方，不是他在说话
        0 = 其他（只在中段出现）→ 不足以判定归属

        例：
            "乙愣了一下，把茶递过来"  → 3（主语）
            "「乙：我去看看」"         → 3
            "乙，你别这样"            → 1（呼语，说话人另有其人）
            "我刚才看见乙了"          → 0（只是被提到）
        """
        t = str(text or "")
        nm = str(name or "")
        if not t or not nm or nm not in t:
            return 0
        i = 0
        while i < len(t) and t[i] in MSG_OWNER_SPEAKER_DECOR:
            i += 1
        if not t.startswith(nm, i):
            return 0
        nxt = t[i + len(nm):i + len(nm) + 1]
        if nxt and nxt in MSG_OWNER_VOCATIVE_CHARS:
            return 1
        return 3

    def _attribute_message_owner(
        self,
        msg_name: Any,
        content: Any,
        card_ref: Any = None,
        speaker: Any = None,
    ) -> Optional[str]:
        """判定一条 message 归属哪个角色（V3 规范 3.1 的四条规则）。

        返回的是**角色名**（永远不是卡名）。判定顺序：

        1. 有 ``name`` 字段 → 用它（不在库里就建档并挂到当前卡下）
        2. ``content`` 形如 ``"角色名：xxx"`` / ``"角色名: xxx"`` → 抠出来
        3. ``content`` 里包含已知的**卡下**角色名 → 用那个（最长优先）
        4. 都没命中 → 当前卡的 ``main_character``，再不行用 ``speaker``
        """
        # 规则 1
        try:
            nm = _relay_fix_text(msg_name).strip()
            if nm:
                # V3：**卡名不是角色** —— 消息不该归属到卡名上
                _cname = _relay_fix_text(card_ref).strip() if card_ref \
                    else str(self._current_card or "").strip()
                if _cname and nm == _cname:
                    self.logger.debug("[中继] 归属：%r 是卡名，不作为角色", nm)
                else:
                    real = self._ensure_character_in_card(nm, card_ref)
                    if real:
                        return real
        except Exception as ex:
            self.logger.warning("[中继] 归属(规则1)失败：%s", ex)

        text = str(content or "")

        # 规则 2
        try:
            for pat in MSG_OWNER_PREFIX_PATTERNS:
                mt = re.match(pat, text)
                if not mt:
                    continue
                cand = _relay_fix_text(mt.group(1)).strip().strip("「」『』\"'")
                if not cand or len(cand) > MSG_OWNER_MAX_NAME_LEN:
                    continue
                if cand in NAME_REJECT_EXACT:
                    continue
                real = self._ensure_character_in_card(cand, card_ref)
                if real:
                    return real
        except Exception as ex:
            self.logger.warning("[中继] 归属(规则2)失败：%s", ex)

        # 规则 3（V3.1 收紧：只认当前卡下的角色名；最长优先，避免"明"吃掉"诸葛小明"）
        #
        # 【为什么收紧】旧实现是「正文里只要出现某个角色名 → 整条归给他」。
        # 一条消息顺口提到别人，就会被判成那个人的发言；写进 messages.name 后，
        # 抽取层看到的就是「乙: <其实是甲说的话>」，LLM 忠实地据此生成
        # 「乙的记忆」→ 张冠李戴，且从记忆内容上完全看不出问题。
        # 现在只认「名字处于说话人位置」（_speaker_position_score）：
        #   正文开头 = 说话人；中段被提到 = 不算；开头但后面跟「，！？」= 呼语，不算。
        # 宁可归属保守（退到规则 4 归给卡主角色 / speaker），也不要张冠李戴。
        try:
            for nm in self._card_character_names(card_ref):
                if not nm:
                    continue
                sc = self._speaker_position_score(text, nm)
                if sc >= MSG_OWNER_MIN_SCORE:
                    self.logger.info(
                        "[中继] 归属(规则3)：正文里 %r 处于说话人位置（score=%d）",
                        nm, sc)
                    return nm
                if sc:
                    self.logger.debug(
                        "[中继] 归属(规则3)弱证据忽略：%r score=%d", nm, sc)
        except Exception as ex:
            self.logger.warning("[中继] 归属(规则3)失败：%s", ex)

        # 规则 4
        try:
            fallback = self._card_main_character(card_ref) \
                or _relay_fix_text(speaker).strip() or None
            if fallback:
                return self._ensure_character_in_card(fallback, card_ref)
        except Exception as ex:
            self.logger.warning("[中继] 归属(规则4)失败：%s", ex)
        return None

    def _assert_owner_is_character(self, owner_id: Any) -> bool:
        """V3 硬性检查：记忆的 owner **必须**指向 ``characters`` 表。

        若有人把 ``card_id`` 当 owner 传进来，这里直接 raise —— 这属于编码
        期错误（不是运行期数据问题），必须立刻暴露，不能静默写脏数据。
        """
        oid = _to_int(owner_id)
        if oid is None or oid <= 0:
            raise ValueError("memory owner 非法：%r" % (owner_id,))
        row = self.db.query_one(
            "SELECT character_id FROM characters WHERE character_id = ?",
            (oid,))
        if row is not None:
            return True
        card = self.db.query_one(
            "SELECT card_id FROM cards WHERE card_id = ?", (oid,))
        if card is not None:
            raise ValueError(
                "memory owner 不能是 card_id：%r 是卡不是角色（V3 铁律）"
                % (oid,))
        raise ValueError("memory owner 指向不存在的角色：%r" % (oid,))

    # ==================================================================
    # 中继：边聊边记（批 10 追加）
    # ==================================================================
    def _commit_turn(
        self,
        character_name: str,
        user_message: str,
        assistant_message: str,
        source: str = "relay",
        card: Optional[str] = None,
        extra_messages: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        """**真正落库**：写入一轮对话并提取记忆（原 ``ingest_turn`` 的正文）。

        V4 起这是「落库」那一段；中继不再直接调它，而是走
        ``ingest_turn_staged()`` → 先暂存，等下一轮请求（或超时）才落库
        （见 ``_stage_turn`` / ``_commit_staged``）。需要**立即写**的
        调用方（CLI / 测试 / 导入）继续用 ``ingest_turn()``，它就是本方法的
        薄包装。

        参数
        ----
        * ``character_name`` —— 当前活跃角色名；库里没有就 ``get_or_create``
          自动注册（新角色第一句话就能建档）
        * ``user_message`` / ``assistant_message`` —— 这一轮用户说的话和
          模型给出的回复
        * ``source`` —— 写进 ``messages.source_file`` 的来源标记，默认 ``relay``
        * ``card`` —— **V3 追加**：当前卡名。只用来分组 / 校验归属，
          **绝不会**被当成记忆的 owner
        * ``extra_messages`` —— **V3 追加**：这一轮里额外的 message
          （``[{"name","content","is_user"}, ...]``）

        流程（每步独立 try/except，出错只记日志，**绝不抛出**）
        -----------------------------------------------------
        1. ``char_mgr.get_or_create(character_name)``
        2. 找 user 角色（``characters.is_user = 1`` 的第一个；没有就创建
           ``"User"`` 并 ``is_user = 1``）
        3. **V3**：遍历这一轮每条 message，用 ``_attribute_message_owner()``
           独立判定它归属哪个角色（规则见该方法），并用
           ``_assert_owner_is_character()`` 硬性校验 owner 指向 characters 表
        4. 生成 message_id 并 ``INSERT OR IGNORE INTO messages``（``processed = 0``）
        5. ``self.extractor.extract_from_messages()`` 抽这一轮
        6. ``self._apply_extraction()`` 按严格顺序落库

        返回
        ----
        并入 ``_apply_extraction`` 统计的 dict：``character`` / ``user`` /
        ``card`` / ``owners`` / ``messages``（本次新写入的 messages 行数）/
        ``skipped_messages``（内容与库中完全相同的重复消息）/ ``memories`` /
        ``events`` / ``beliefs`` / ``total`` / ``errors`` / ``skipped`` /
        ``extract_mode`` …
        """
        stats: Dict[str, Any] = {
            "source": str(source or RELAY_INGEST_SOURCE),
            "character": "", "user": "", "card": str(card or ""),
            "owners": [],
            "messages": 0, "skipped_messages": 0,
            "memories": 0, "memories_new": 0, "memories_reused": 0,
            "events": 0, "beliefs": 0, "knowledge": 0,
            "commitments": 0, "secrets": 0, "visibility": 0,
            "relationship_changes": 0, "state_changes": 0,
            "total": 0, "skipped": [], "errors": 0,
            "extract_mode": "", "extract_source": "",
        }

        user_text = _relay_fix_text(user_message).strip()
        assistant_text = _relay_fix_text(assistant_message).strip()

        # [时间层] 从 user 消息里抓剧情时间戳，更新 conversation_meta
        try:
            self._update_story_time(user_text, card=card)
        except Exception as ex:
            self.logger.warning("[时间] 更新失败（已忽略）：%s", ex)

        # [场景层] 从 assistant 输出里抽 📍/🎭，经仲裁后存 conversation_meta
        try:
            _new_scene = self._extract_scene_from_assistant(assistant_text)
            # ★ 场景过滤 + 单角色兜底
            #  1) 只认本卡已登记角色名（防卡模板里 👀神态/👘穿着 被当成"角色名：位置"）
            #  2) 单角色卡（如戊）的 📍 **地点**：X 格式，用 default 兜底
            _card_for_scene = (str(card or "").strip()
                               or str(getattr(self, "_current_card", "") or ""))
            _known_names = set()
            try:
                _known_names = set(self._card_character_names(_card_for_scene) or [])
                _known_names |= set(self._current_card_actors or [])
            except Exception:
                pass
            if _known_names:
                for _k in ("locations", "actions"):
                    _src = _new_scene.get(_k) or {}
                    _bad = [k for k in _src if k not in _known_names]
                    if _bad:
                        _new_scene[_k] = {k: v for k, v in _src.items() if k in _known_names}
                        self.logger.info("[场景] 过滤非本卡角色：%s = %s", _k, _bad)
                # 单角色兜底：只有一个角色 且 过滤后 locations 为空 → 从 📍 行取值
                if (not _new_scene.get("locations")
                        and len(_known_names) == 1
                        and not _new_scene.get("actions")):
                    _only_name = next(iter(_known_names))
                    try:
                        import re as _re_loc
                        for _ln in str(assistant_text or "").split("\n"):
                            _s = _ln.strip()
                            if _s.startswith("📍"):
                                _mm = _re_loc.search(r"[：:]\s*(.+)$", _s)
                                if _mm:
                                    _loc = _mm.group(1).strip().strip("*").strip()
                                    if _loc and len(_loc) <= 60:
                                        _new_scene["locations"] = {_only_name: _loc}
                                        self.logger.info(
                                            "[场景] 单角色兜底：%s -> %r", _only_name, _loc)
                                        break
                    except Exception as _ex_solo:
                        self.logger.warning("[场景] 单角色兜底失败：%s", _ex_solo)
            if _new_scene.get("locations") or _new_scene.get("actions"):
                _card_for_scene = str(card or "").strip() or str(
                    getattr(self, "_current_card", "") or "")
                if _card_for_scene:
                    _old_scene = self._load_scene_state(_card_for_scene)
                    _exempt = self._user_mentioned_names(
                        user_text, _card_for_scene)
                    _merged, _stats = self._merge_scene(
                        _old_scene, _new_scene, assistant_text, _exempt)
                    self._save_scene_state(_card_for_scene, _merged)
                    self.logger.info(
                        "[场景] 已更新 card=%s loc=%d act=%d "
                        "仲裁更新=%d 拦截=%d",
                        _card_for_scene,
                        len(_merged.get("locations") or {}),
                        len(_merged.get("actions") or {}),
                        _stats.get("updated", 0),
                        _stats.get("blocked", 0))
        except Exception as ex:
            self.logger.warning("[场景] 抽取失败（已忽略）：%s", ex)

        if not user_text and not assistant_text:
            stats["skipped"].append("这一轮没有内容")
            return stats

        # ---- 1) 角色：没有就自动注册 ----
        char_row: Optional[Dict[str, Any]] = None
        try:
            char_row = _relay_get_or_create(
                self, str(character_name or "").strip(), self.logger)
        except Exception as ex:
            self.logger.warning("[中继] 已回写：角色 %r 注册失败：%s",
                                character_name, ex)
        if char_row is None:
            stats["skipped"].append("角色无效：%r" % (character_name,))
            self.logger.warning("[中继] 已回写：跳过了（角色无效 %r）",
                                character_name)
            return stats
        char_name = str(char_row.get("name") or character_name)
        char_id = _to_int(char_row.get("character_id"))
        stats["character"] = char_name

        # ---- 1b) V3：卡（只做分组，不参与 owner）----
        card_name: Optional[str] = _relay_fix_text(card).strip() or None
        if card_name:
            try:
                if self.card_mgr.get_or_create(card_name):
                    self.remember_card_name(card_name)
            except Exception as ex:
                self.logger.warning("[中继] 已回写：建卡 %r 失败：%s",
                                    card_name, ex)
        stats["card"] = card_name or ""
        # V3：本轮回写的卡名 —— 后面判"卡名不是角色"要用（记忆/信念/知识守卫）
        self._current_card = card_name or ""

        # ---- 2) user 角色 ----
        user_row: Optional[Dict[str, Any]] = None
        try:
            user_row = self.char_mgr.get_user()
        except Exception as ex:
            self.logger.warning("[中继] 已回写：查询 user 角色失败：%s", ex)
        if user_row is None:
            try:
                user_row = self.char_mgr.get_or_create(
                    RELAY_INGEST_USER_NAME, is_user=True)
                if user_row is not None:
                    self.logger.info("[中继] 已回写：库里没有 user 角色，"
                                     "已创建 %s", RELAY_INGEST_USER_NAME)
            except Exception as ex:
                self.logger.warning("[中继] 已回写：创建 user 角色失败：%s", ex)
        user_name = str((user_row or {}).get("name") or RELAY_INGEST_USER_NAME)
        user_id = _to_int((user_row or {}).get("character_id"))
        stats["user"] = user_name

        # ---- 3) V3：这一轮每条 message 独立判归属 ----
        # 默认两条（user + 中继识别出的说话人）；中继传了 extra_messages 就一并纳入。
        turn: List[Dict[str, Any]] = []
        if user_text:
            turn.append({"name": user_name, "content": user_text,
                         "is_user": True})
        if assistant_text:
            # [归属修复] assistant 回复里有角色标记（💗甲 / 💗丙 …）就
            # 按标记拆成多条，每条**直接用标记里的名字**，不再靠中继推断的说话人
            # —— 实测中继把「甲视角的整条回复」整条记在了丙名下。
            # 没标记的开头段（正文）拿第一个被点名的角色；一个标记都没有
            # （普通单角色回复）→ 保持原行为，用中继识别出的说话人。
            _segs = self._split_assistant_segments(assistant_text, card_name)
            if len(_segs) <= 1 and not _segs[0][0]:
                turn.append({"name": char_name, "content": _segs[0][1],
                             "is_user": bool(char_row.get("is_user"))})
            else:
                _first_named = None
                for _n, _ in _segs:
                    if _n:
                        _first_named = _n
                        break
                if not _first_named:
                    try:
                        _first_named = self._card_main_character(card_name)
                    except Exception:
                        _first_named = None
                _fb = _first_named or char_name
                for _n, _body in _segs:
                    _nm = _n or _fb
                    turn.append({"name": _nm, "content": _body,
                                 "is_user": bool(char_row.get("is_user")),
                                 "_direct": True,
                                 "_marker": bool(_n)})
                self.logger.info(
                    "[中继] 归属：assistant 按角色标记拆 %d 条 → %s",
                    len(_segs), [_n or ("(%s)" % _fb) for _n, _ in _segs])
        for item in (extra_messages or []):
            if not isinstance(item, dict):
                continue
            txt = _relay_fix_text(item.get("content")).strip()
            if not txt:
                continue
            turn.append({"name": item.get("name"), "content": txt,
                         "is_user": bool(item.get("is_user"))})

        # rows_to_write: (message_id, name, text, is_user, character_id, position)
        rows_to_write: List[Tuple[str, str, str, int, Optional[int], int]] = []
        for pos, item in enumerate(turn):
            text = str(item.get("content") or "")
            is_user_msg = bool(item.get("is_user"))
            owner: Optional[str] = None
            if item.get("_direct") and item.get("name"):
                # 标记直接定名 —— 不做任何推断
                owner = str(item.get("name")).strip()
            else:
                try:
                    owner = self._attribute_message_owner(
                        item.get("name"), text,
                        card_ref=card_name, speaker=char_name)
                except Exception as ex:
                    self.logger.warning("[中继] 归属判定异常（回退默认）：%s", ex)

            if owner:
                owner_row = self.char_mgr.get(owner)
            else:
                owner, owner_row = (user_name, user_row) if is_user_msg \
                    else (char_name, char_row)

            oid = _to_int((owner_row or {}).get("character_id"))
            if oid is None:
                owner, oid = (user_name, user_id) if is_user_msg \
                    else (char_name, char_id)

            # V3 硬性检查：owner 必须指向 characters 表（card_id 一律拒绝）
            try:
                self._assert_owner_is_character(oid)
            except ValueError as ex:
                stats["errors"] += 1
                self.logger.error("[中继] 已回写：归属检查未通过，跳过这条：%s",
                                  ex)
                continue

            if not is_user_msg and bool((owner_row or {}).get("is_user")):
                is_user_msg = True
            rows_to_write.append(
                (_relay_turn_message_id(owner, text), owner, text,
                 1 if is_user_msg else 0, oid, pos))

        stats["owners"] = [r[1] for r in rows_to_write]
        if rows_to_write:
            self.logger.info(
                "[中继] 已回写：card=%s 本轮归属=%s",
                card_name or "（无）", stats["owners"])

        # ---- 4) 写入 messages（processed = 0）----
        now = now_iso()
        try:
            with self.db.transaction():
                for mid, name, text, is_user, cid, pos in rows_to_write:
                    if not text:
                        continue
                    cur = self.db.execute(
                        "INSERT OR IGNORE INTO messages "
                        "(message_id, source_file, source_position, name, "
                        " is_user, is_system, mes, send_date, character_id, "
                        " imported_at, processed) "
                        "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 0)",
                        (mid, stats["source"], pos, name, is_user, text,
                         now, cid, now))
                    if cur is None:
                        stats["errors"] += 1
                        continue
                    if (cur.rowcount or 0) <= 0:
                        # 同角色同内容已经记过（message_id 是内容指纹）
                        stats["skipped_messages"] += 1
                        self.logger.info(
                            "[中继] 已回写：消息已存在（同角色同内容），跳过 %s",
                            mid)
                        continue
                    stats["messages"] += 1
                    if cid is not None:
                        try:
                            self.char_mgr.increment_message_count(cid, 1)
                        except Exception:
                            pass
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[中继] 已回写：写入 messages 异常：%s", ex)

        # ---- 5) 抽取（V3：按归属后的角色喂给抽取器，LLM 失败自动回退规则）----
        result: Optional[ExtractionResult] = None
        try:
            extract_input = [
                {"name": mid[1], "content": mid[2],
                 "is_user": bool(mid[3]), "message_id": mid[0]}
                for mid in rows_to_write
            ]
            if not extract_input:
                extract_input = [
                    {"name": user_name, "content": user_text,
                     "is_user": True,
                     "message_id": _relay_turn_message_id(user_name, user_text)},
                    {"name": char_name, "content": assistant_text,
                     "is_user": bool(char_row.get("is_user")),
                     "message_id": _relay_turn_message_id(char_name,
                                                          assistant_text)},
                ]
            result = self.extractor.extract_from_messages(
                extract_input, mode=DEFAULT_MODE,
                roster=self._extraction_roster_text())
            stats["extract_mode"] = str(getattr(result, "mode", "") or "")
            stats["extract_source"] = str(getattr(result, "source", "") or "")
        except Exception as ex:
            stats["errors"] += 1
            self.logger.exception("[中继] 已回写：抽取异常：%s", ex)

        # ---- 6) 落库 ----
        def _table_count(table: str) -> int:
            """COUNT(*) ；失败返回 -1（用于算真实新增行数）。"""
            try:
                rows = self.db.query("SELECT COUNT(*) AS n FROM %s" % table)
                if rows:
                    return int((rows[0] or {}).get("n") or 0)
            except Exception:
                pass
            return -1

        mem_before = _table_count("memories")
        if result is not None:
            try:
                applied = self._apply_extraction(result, extract_input)
                for key in ("memories", "events", "beliefs", "knowledge",
                            "commitments", "secrets", "visibility",
                            "relationship_changes", "state_changes", "total"):
                    if key in applied:
                        stats[key] = applied[key]
                stats["errors"] += int(applied.get("errors") or 0)
                for sk in (applied.get("skipped") or []):
                    stats["skipped"].append(sk)
            except Exception as ex:
                stats["errors"] += 1
                self.logger.exception("[中继] 已回写：落库异常：%s", ex)

        # 「新增记忆」按**表里真实多出来的行数**算：重复内容会被
        # ``MemoryManager.add_memory`` 按 dedup_hash 复用旧行（既有的幂等设计），
        # 那种情况不该算新增，只记为「复用」。
        mem_after = _table_count("memories")
        if mem_before >= 0 and mem_after >= 0:
            stats["memories_new"] = max(0, mem_after - mem_before)
        else:
            stats["memories_new"] = int(stats.get("memories") or 0)
        stats["memories_reused"] = max(
            0, int(stats.get("memories") or 0) - int(stats["memories_new"]))

        self.logger.info(
            "[中继] 已回写：角色=%s, user=%d 字, assistant=%d 字, 新增记忆=%d 条",
            char_name, len(user_text), len(assistant_text),
            int(stats.get("memories_new") or 0))
        self.logger.debug(
            "[中继] 已回写明细：messages=%d(重复跳过 %d) 事件=%d 信念=%d "
            "承诺=%d 可见性=%d 记忆复用 %d 抽取=%s/%s 错误=%d",
            stats["messages"], stats["skipped_messages"], stats["events"],
            stats["beliefs"], stats["commitments"], stats["visibility"],
            stats["memories_reused"], stats["extract_mode"],
            stats["extract_source"], stats["errors"])
        # V3：本轮结束 —— 清掉当前卡，避免串到下一张卡
        # V5.6/V5.8：【时间感知】开关、【演员】名单跟 _current_card 同生命周期
        self._current_card = ""
        self._current_time_aware = False
        self._current_card_actors = []
        return stats

    # ==================================================================
    # V4：延迟一拍写库（reroll 的旧版本永不入库）
    # ==================================================================
    def _pending_timeout(self) -> float:
        """暂存超时秒数（``llm.stage_commit_timeout``，读不到用 600）。"""
        try:
            v = float(getattr(self.config.llm, "stage_commit_timeout",
                              PENDING_DEFAULT_TIMEOUT)
                      or PENDING_DEFAULT_TIMEOUT)
            return v if v > 0 else PENDING_DEFAULT_TIMEOUT
        except Exception:
            return PENDING_DEFAULT_TIMEOUT

    def _load_pending(self) -> Optional[Dict[str, Any]]:
        """读暂存轮次（``conversation_meta['pending_turn']``）；没有返回 None。"""
        try:
            raw = self.db.get_meta(PENDING_META_KEY)
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception as ex:
            self.logger.warning("[中继] 暂存读取失败（忽略）：%s", ex)
            return None

    @staticmethod
    def _pending_age(pending: Dict[str, Any]) -> float:
        """暂存距今多少秒（**按首次暂存时间 `pending_first_ts` 算**）；
        时间戳缺失按「很旧」处理（= 会被落库）。
        回退读 `pending_at_ts` 只为兼容 A2 之前写下的旧暂存。"""
        try:
            ts = float(pending.get("pending_first_ts")
                       or pending.get("pending_at_ts") or 0.0)
        except Exception:
            ts = 0.0
        if ts <= 0:
            return float(PENDING_DEFAULT_TIMEOUT) + 1.0
        return max(0.0, time.time() - ts)

    def _clear_pending(self) -> None:
        """清掉暂存（主键 + 各字段的独立键）。"""
        keys = (PENDING_META_KEY,) + tuple(PENDING_FIELDS)
        try:
            self.db.execute(
                "DELETE FROM conversation_meta WHERE key IN (%s)"
                % ",".join("?" * len(keys)), tuple(keys))
        except Exception as ex:
            self.logger.warning("[中继] 暂存清理失败（忽略）：%s", ex)

    def _stage_turn(
        self,
        character_name: Any,
        user_message: Any,
        assistant_message: Any,
        card: Any = None,
        source: Any = None,
        extra_messages: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        """**暂存不写库**：把这一轮记进 ``conversation_meta``。

        写入 ``pending_turn``（整段 JSON，原子）+ 每个字段一份独立键，
        字段名见 ``PENDING_FIELDS``：``pending_user_msg_id``（user 消息指纹）/
        ``pending_user_text`` / ``pending_assistant_text`` / ``pending_character``
        / ``pending_card`` / ``pending_source`` / ``pending_at``。

        **不碰 messages / memories / events**，所以 reroll 掉的那些版本
        永远不会进库。返回暂存记录（``staged`` 标记成功与否）。
        """
        user_text = _relay_fix_text(user_message).strip()
        assistant_text = _relay_fix_text(assistant_message).strip()
        char_name = _relay_fix_text(character_name).strip()
        # V5.2：调用方没给卡名时，退回「当前请求刚识别出的卡」——
        #       保证 pending 里一定记着这次该挂哪张卡，下次落库才能恢复。
        card_name = (_relay_fix_text(card).strip()
                     or str(self._current_card or "").strip())
        # [A2] 双时间戳防死锁：pending_first_ts = 这一轮 user 正文「第一次」被暂存的时间。
        #      指纹相同（reroll）时保留旧值 → _pending_age 会一直往上涨，
        #      600 秒逃生通道才走得通（旧实现每次 reroll 都刷 pending_at_ts，age 永远归零）。
        _fp = _relay_user_fingerprint(user_text)
        _prev = self._load_pending() or {}
        _same = str(_prev.get("pending_user_msg_id") or "") == _fp
        _first = _prev.get("pending_first_ts") if _same else None
        if not _first:
            _first = time.time()
        rec: Dict[str, Any] = {
            "pending_user_msg_id": _fp,
            "pending_user_text": user_text,
            "pending_assistant_text": assistant_text,
            "pending_character": char_name,
            "pending_card": card_name,
            "pending_source": str(source or RELAY_INGEST_SOURCE),
            "pending_at": now_iso(),
            "pending_at_ts": time.time(),
            "pending_first_ts": _first,
        }
        if extra_messages:
            rec["pending_extra_messages"] = [
                dict(m) for m in extra_messages if isinstance(m, dict)]
        try:
            self.db.set_meta(PENDING_META_KEY, _json_dumps(rec))
            for key in PENDING_FIELDS:
                self.db.set_meta(key, str(rec.get(key) or ""))
        except Exception as ex:
            self.logger.warning("[中继] 暂存写入失败（忽略）：%s", ex)
            return {"staged": False, "reason": "%s: %s" % (type(ex).__name__, ex)}
        self.logger.info(
            "[中继] 暂存：card=%s 角色=%s user=%d 字 assistant=%d 字"
            "（指纹=%s，未落库）",
            card_name or "（无）", char_name or "（无）",
            len(user_text), len(assistant_text), rec["pending_user_msg_id"])
        return rec

    def _find_adopted_assistant(self, messages: Any,
                                user_text: Any) -> Optional[str]:
        """**V5 核心**：从下次请求的历史里，读出用户**实际留下**的那版 assistant。

        * 在当前请求的 ``messages`` 里找 ``role=user`` 且**内容相等**
          （不看 message_id —— Tavo 没有稳定 id）的那条；多条命中取**最后一条**
        * 取它**紧随其后**的那条 ``role=assistant`` 的 content
        * 找不到 / 后面不是 assistant / 内容为空 → 返回 None
          （调用方退回暂存里的那一版，即 V4 行为）
        """
        try:
            want = _relay_fix_text(user_text).strip()
            if not want or not messages:
                return None
            pairs: List[Tuple[str, str]] = []
            for m in messages:
                if not isinstance(m, dict):
                    continue
                pairs.append((str(m.get("role") or "").strip().lower(),
                              _relay_fix_text(m.get("content"))))
            hit = None
            for i, (role, content) in enumerate(pairs):
                if role == "user" and content.strip() == want:
                    hit = i                      # 取最后一条（reroll 会有多条）
            if hit is None or hit + 1 >= len(pairs):
                return None
            role2, content2 = pairs[hit + 1]
            if role2 != "assistant":
                return None
            txt = str(content2 or "").strip()
            return txt or None
        except Exception as ex:
            self.logger.warning("[中继] 历史匹配异常（退回暂存版）：%s", ex)
            return None

    def _commit_staged(self, pending: Optional[Dict[str, Any]],
                       messages: Any = None) -> Dict[str, Any]:
        """把暂存的那一轮**真正落库**（走 ``_commit_turn`` 全流程）。

        **V5**：落库前先拿下次请求的 ``messages`` 去核对 —— 用历史里
        user 消息后面**实际跟着的那版 assistant**，而不是「最后一次生成的」。
        """
        if not isinstance(pending, dict) or not pending:
            return {}
        user_text = str(pending.get("pending_user_text") or "")
        staged_text = str(pending.get("pending_assistant_text") or "")
        # V5.1 兜底：暂存里的角色若是「用户 / 卡名」（旧版本代码留下的暂存，
        # 比如 角色=明），落库前改从那张卡的 main_character 里重挑；
        # 挑不到就丢弃这条暂存 —— 绝不把用户当说话人写进 messages。
        _pchar = str(pending.get("pending_character") or "").strip()
        if _pchar and self._should_skip_character(_pchar):
            _alt = self._reselect_speaker(pending.get("pending_card"), None)
            if _alt:
                self.logger.info(
                    "[中继] 暂存落库：角色=%r 命中用户/卡名过滤，改用 %r",
                    _pchar, _alt)
                pending = dict(pending)
                pending["pending_character"] = _alt
            else:
                self.logger.info(
                    "[中继] 暂存落库：角色=%r 命中用户/卡名过滤且无卡可改选，"
                    "丢弃这条暂存（不写库）", _pchar)
                self._clear_pending()
                return {}
        adopted = self._find_adopted_assistant(messages, user_text)
        if adopted:
            self.logger.info(
                "[中继] 采纳：历史里 user（%s…）后面那版 assistant %d 字，"
                "用它落库（暂存里是 %d 字）",
                user_text[:12], len(adopted), len(staged_text))
            assistant_text = adopted
        else:
            self.logger.info(
                "[中继] 历史里找不到「%s…」，用暂存版（%d 字）",
                user_text[:12], len(staged_text))
            assistant_text = staged_text
        # ---- V5.2：落库前恢复「这一轮该挂哪张卡」----
        #   延迟一拍后，抽取是在**下一次请求**里跑的：此刻 self._current_card
        #   已经是空的了（上一次落库结束时清过），于是 _ensure_character()
        #   看不到当前卡，抽取阶段新发现的角色就散装（card_id=None）。
        #   这里把卡名从 pending 里恢复出来（pending 没记就退回当前请求的卡），
        #   落完再清掉，避免串给后面的识别。
        prev_card = (str(pending.get("pending_card") or "").strip()
                     or str(self._current_card or "").strip())
        self.logger.debug("[中继] 落库前恢复 _current_card=%r（pending_card=%r）",
                          prev_card, pending.get("pending_card"))
        try:
            stats = self._commit_turn(
                str(pending.get("pending_character") or ""),
                user_text,
                assistant_text,
                source=str(pending.get("pending_source") or RELAY_INGEST_SOURCE),
                card=(prev_card or None),
                extra_messages=pending.get("pending_extra_messages"))
        except Exception as ex:
            self.logger.exception("[中继] 暂存落库失败（已忽略）：%s", ex)
            self._clear_pending()
            return {}
        finally:
            self._current_card = ""
            self._current_time_aware = False
            self._current_card_actors = []
        self.logger.info(
            "[中继] 暂存落库：card=%s 角色=%s 新增记忆=%d 条"
            "（暂存于 %s，指纹=%s）",
            (pending.get("pending_card") or "（无）"),
            (pending.get("pending_character") or "（无）"),
            int((stats or {}).get("memories_new") or 0),
            pending.get("pending_at") or "?", pending.get("pending_user_msg_id"))
        self._clear_pending()
        return stats

    def ingest_turn_staged(
        self,
        character_name: str,
        user_message: str,
        assistant_message: str,
        source: str = "relay",
        card: Optional[str] = None,
        extra_messages: Optional[Sequence[Any]] = None,
        messages: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        """**V4/V5 中继入口**：先处理上一轮暂存，再暂存本轮（都不立刻写库）。

        1. 没有暂存 → 只暂存本轮
        2. 指纹与本轮相同（reroll）且未超时 → **覆盖暂存，一行都不写**
        3. 指纹不同（用户换了新话）→ 先落库上一轮，再暂存本轮
        4. 指纹相同但已超时（默认 600 秒）→ 同样先落库上一轮，再暂存本轮
        5. ``llm.deferred_ingest=false`` → 退回旧行为（立即落库）

        **V5**：落库上一轮时用 ``messages``（本次请求的原始历史）核对，
        落的是用户**实际留在界面上**的那版 assistant。
        """
        user_text = _relay_fix_text(user_message).strip()
        assistant_text = _relay_fix_text(assistant_message).strip()
        char_name = str(character_name or "").strip()
        if not user_text:
            self.logger.warning(
                "[中继] 本轮 user 正文为空（指纹会恒定 → 可能一直判成 reroll、"
                "永不落库）：card=%s 角色=%s assistant=%d 字",
                card, char_name, len(assistant_text))
        if not user_text and not assistant_text:
            return {"staged": False, "reason": "这一轮没有内容"}
        if not char_name:
            return {"staged": False, "reason": "缺少角色"}

        if not bool(getattr(self.config.llm, "deferred_ingest", True)):
            self.logger.debug("[中继] deferred_ingest=false，立即落库（旧行为）")
            return self._commit_turn(char_name, user_text, assistant_text,
                                     source=str(source or RELAY_INGEST_SOURCE),
                                     card=card, extra_messages=extra_messages)

        fp = _relay_user_fingerprint(user_text)
        if not user_text:
            # 兜底：user 正文为空时指纹恒定 → 每轮都被判成 reroll、永不落库。
            # 退用「历史条数」当指纹：真 reroll 历史条数不变（仍挡得住），
            # 用户往前走了条数就会变（能落库）。
            fp = _relay_user_fingerprint("\x00count=%d" % len(list(messages or [])))
        pending = self._load_pending()
        if pending:
            same = str(pending.get("pending_user_msg_id") or "") == fp
            age = self._pending_age(pending)
            timeout = self._pending_timeout()
            if same and age <= timeout:
                self.logger.info(
                    "[中继] 暂存：user 消息与上一条相同（reroll），"
                    "覆盖暂存、不写库（指纹=%s，已过 %.1f 秒）", fp, age)
            else:
                if same:
                    self.logger.info(
                        "[中继] 暂存：同一句但已过 %.1f 秒（>%.0f 秒），"
                        "先把上一条落库", age, timeout)
                else:
                    self.logger.info(
                        "[中继] 暂存：user 消息变了（%s -> %s），"
                        "说明上一条已被采纳，先落库",
                        pending.get("pending_user_msg_id") or "?", fp)
                self._commit_staged(pending, messages=messages)
        return self._stage_turn(char_name, user_text, assistant_text,
                                card=card, source=source,
                                extra_messages=extra_messages)

    def ingest_turn(
        self,
        character_name: str,
        user_message: str,
        assistant_message: str,
        source: str = "relay",
        card: Optional[str] = None,
        extra_messages: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        """**立即写库**（V4 前的中继行为；CLI / 测试 / 导入继续用它）。

        等价于 ``_commit_turn(...)``；中继走的是 ``ingest_turn_staged()``。
        """
        return self._commit_turn(character_name, user_message, assistant_message,
                                 source=source, card=card,
                                 extra_messages=extra_messages)

    def apply_decay(self, rate: Optional[float] = None) -> int:
        """施加一次记忆衰减；``decay_enabled=False`` 且未显式传 rate 时跳过。"""
        if rate is None and not self.config.memory.decay_enabled:
            self.logger.info("[引擎] decay_enabled=False，跳过衰减")
            return 0
        try:
            return int(self.mem_mgr.apply_decay(rate))
        except Exception as ex:
            self.logger.exception("[引擎] 衰减失败：%s", ex)
            return 0

    def consolidate_all(
        self,
        mode: Optional[str] = None,
        threshold: Optional[int] = None,
        check_overdue: bool = True,
        allow_nested: Optional[bool] = None,
        manual_trigger: bool = False,
    ) -> Dict[str, Any]:
        """全库记忆压缩（原始记忆永不删除），顺带刷新逾期承诺。

        ``mode`` 接受 **CLI 档位** ``fast`` / ``normal`` / ``deep``，也兼容
        直接传落库值 ``raw`` / ``llm``：

        * ``fast``            -> ``consolidated_mode='raw'``（拼接 + 300 字截断）
        * ``normal``          -> ``consolidated_mode='llm'``（失败自动回退 raw）
        * ``deep``            -> ``consolidated_mode='llm'`` 且**允许二次整合**
          （``is_consolidated=1`` 的摘要也能再被压缩一层）
        """
        raw_mode = str(mode or MODE_FAST).strip().lower()
        if raw_mode in VALID_MODES:
            cmode = (CONSOLIDATED_MODE_RAW if raw_mode == MODE_FAST
                     else CONSOLIDATED_MODE_LLM)
            nested = bool(allow_nested) or raw_mode == MODE_DEEP
        elif raw_mode in VALID_CONSOLIDATED_MODES:
            cmode = raw_mode
            nested = bool(allow_nested)
        else:
            self.logger.warning("[引擎] 未知压缩 mode=%r，回落 %s",
                                mode, CONSOLIDATED_MODE_RAW)
            cmode = CONSOLIDATED_MODE_RAW
            nested = False

        if threshold is None:
            threshold = int(self.config.memory.consolidate_threshold or 5)
        threshold = max(2, int(threshold))

        made = 0
        try:
            if nested:
                made = self._consolidate_nested(cmode, threshold,
                                                manual_trigger=manual_trigger)
            else:
                made = int(self.mem_mgr.consolidate_all(
                    mode=cmode, threshold=threshold,
                    manual_trigger=manual_trigger))
        except Exception as ex:
            self.logger.exception("[引擎] 压缩失败：%s", ex)

        overdue: List[Dict[str, Any]] = []
        if check_overdue:
            try:
                overdue = self.commit_mgr.check_overdue(mark_expired=True)
            except Exception as ex:
                self.logger.exception("[引擎] 逾期承诺检查失败：%s", ex)
        return {"mode": cmode, "threshold": threshold, "nested": nested,
                "consolidated": made, "overdue": len(overdue)}

    def _consolidate_nested(self, cmode: str, threshold: int,
                            max_rounds: int = 100,
                            manual_trigger: bool = False) -> int:
        """deep 档：允许摘要被再次压缩（每角色最多 ``max_rounds`` 轮，防死循环）。"""
        owners = self.db.query(
            "SELECT DISTINCT owner_character_id AS cid FROM memories")
        made = 0
        for r in owners:
            rounds = 0
            while rounds < max_rounds:
                out = self.mem_mgr.consolidate(
                    r["cid"], threshold=threshold, mode=cmode,
                    allow_nested=True, manual_trigger=manual_trigger)
                if out is None:
                    break
                made += 1
                rounds += 1
        self.logger.info("[引擎] deep 压缩完成：新增摘要 %d 条（含二次整合）", made)
        return made

    def detect_all_conflicts(
        self,
        threshold: float = CONFLICT_SIMILARITY_THRESHOLD,
        owner: Any = None,
    ) -> Dict[str, Any]:
        """对所有角色跑一遍记忆冲突检测（只建 ``memory_conflicts`` 记录，
        **绝不删除或覆盖任何旧记忆**）。"""
        total = 0
        per_char: Dict[str, int] = {}
        targets: List[Any] = []
        try:
            if owner is not None:
                targets = [owner]
            else:
                targets = [c["character_id"]
                           for c in self.char_mgr.all(active_only=False)]
        except Exception as ex:
            self.logger.exception("[引擎] 冲突检测取角色失败：%s", ex)
            return {"open_conflicts": 0, "per_character": {}, "error": str(ex)}

        for cid in targets:
            try:
                n = int(self.mem_mgr.detect_conflicts(cid, threshold))
            except Exception as ex:
                self.logger.exception("[引擎] 角色 %s 冲突检测失败：%s", cid, ex)
                n = 0
            if n:
                per_char[str(cid)] = n
            total += n

        try:
            opened = len(self.mem_mgr.list_conflicts(
                status=CONFLICT_STATUS_OPEN))
        except Exception:
            opened = 0
        self.logger.info("[引擎] 冲突检测完成：新建 %d，待裁决 %d", total, opened)
        return {"new_conflicts": total, "open_conflicts": opened,
                "per_character": per_char}

    # ==================================================================
    # 统计
    # ==================================================================
    def summary_stats(self) -> Dict[str, Any]:
        """全库统计（Web ``/api/stats`` 与 CLI ``stats`` 共用）。"""
        def _c(table: str) -> int:
            try:
                return int(self.db.count(table))
            except Exception:
                return 0

        out: Dict[str, Any] = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "db_path": str(self.config.db_path),
            "characters": self.char_mgr.count(),
            "cards": self.card_mgr.count(),
            "loose_characters": self.card_mgr.loose_count(),
            "messages": self.importer.message_count(),
            "unprocessed": self.importer.unprocessed_count(),
            "events": self.event_mgr.count(),
            "event_visibility": _c("event_visibility"),
            "memories": self.mem_mgr.count(),
            "knowledge": self.know_mgr.count(),
            "beliefs": self.belief_mgr.count(),
            "relationships": self.rel_mgr.count(),
            "character_states": self.state_mgr.count(),
            "commitments": self.commit_mgr.count(),
            "secrets": self.secret_mgr.count(),
            "associations": self.assoc_mgr.count(),
            "event_chains": _c("event_chains"),
            "memory_conflicts": _c("memory_conflicts"),
            "llm_enabled": bool(self.llm.enabled),
            "runtime": dict(self.runtime_stats),
        }
        try:
            out["memory_status"] = self.db.query(
                "SELECT status, COUNT(*) AS n FROM memories GROUP BY status")
            out["visibility_by_state"] = self.db.query(
                "SELECT state, COUNT(*) AS n FROM event_visibility "
                "GROUP BY state")
            out["beliefs_by_kind"] = self.db.query(
                "SELECT kind, COUNT(*) AS n FROM beliefs GROUP BY kind")
        except Exception as ex:
            self.logger.warning("[引擎] 统计明细查询失败：%s", ex)
        return out

    def list_characters(self, with_counts: bool = True) -> List[Dict[str, Any]]:
        """角色列表；``with_counts=True`` 时附带记忆数 / 关系数。"""
        try:
            rows = self.char_mgr.all(active_only=False)
        except Exception as ex:
            self.logger.exception("[引擎] 角色列表失败：%s", ex)
            return []
        if not with_counts:
            return rows
        for row in rows:
            cid = row.get("character_id")
            try:
                row["memory_count"] = self.mem_mgr.count(cid)
            except Exception:
                row["memory_count"] = 0
            try:
                row["belief_count"] = self.belief_mgr.count(cid)
            except Exception:
                row["belief_count"] = 0
            try:
                row["knowledge_count"] = self.know_mgr.count(cid)
            except Exception:
                row["knowledge_count"] = 0
        return rows

    # ==================================================================
    # [V6 阶段D] 安全聚合合并（粗筛 difflib + LLM 终审；宁可放弃，绝不拼接）
    # ==================================================================
    @staticmethod
    def _merge_text(content: Any, max_len: int = TEXT_TRUNCATE_LEN) -> str:
        """截断文本。

        ``max_len`` 缺省 ``TEXT_TRUNCATE_LEN``（500，粗筛用）；
        终审喂给 LLM 时传 ``MERGE_VERDICT_TRUNCATE_LEN``（1000）。
        """
        return str(content or "").strip()[:max_len]

    @staticmethod
    def _merge_ratio(a: Any, b: Any) -> float:
        """difflib 字符级相似度（截断后比对），∈[0,1]。"""
        sa = MemoryEngine._merge_text(a)
        sb = MemoryEngine._merge_text(b)
        if not sa or not sb:
            return 0.0
        if sa == sb:
            return 1.0
        return float(SequenceMatcher(None, sa, sb).ratio())

    def _merge_window_groups(self, rows: Sequence[Dict[str, Any]]
                             ) -> List[Tuple[int, int, List[Dict[str, Any]]]]:
        """粗筛第一步：``owner -> tier -> 30 天滑动窗口`` 分桶。

        * 分桶键是 ``owner_character_id``：本引擎里「一条会话 = 一个角色」，
          记忆表**没有** chat_id 列，owner 就是会话归属；跨角色的记忆
          永远不许进同一组（防串记忆）。
        * 窗口以本窗口**第一条**的时间为锚，后续记忆与锚相差超过
          ``MERGE_TIME_WINDOW_DAYS`` 天就开新窗口（滑动窗口，避免刚好卡在
          30 天边界上的两条相似记忆被拆散）。
        * 解析不出 ``created_at`` 的行不参与窗口判定（留在当前窗口）。
        """
        ordered = sorted(rows, key=lambda r: str(r.get("created_at") or ""))
        buckets: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for r in ordered:
            cid = _to_int(r.get("owner_character_id"))
            if cid is None:
                continue
            tier = _to_int(r.get("tier"))
            if tier not in VALID_TIERS:
                tier = DEFAULT_TIER
            buckets.setdefault((int(cid), int(tier)), []).append(r)

        windows: List[Tuple[int, int, List[Dict[str, Any]]]] = []
        for (cid, tier), items in buckets.items():
            cur: List[Dict[str, Any]] = []
            anchor: Optional[datetime] = None
            for it in items:
                dt = _parse_iso(it.get("created_at"))
                if cur and dt is not None and anchor is not None:
                    gap = (dt - anchor).total_seconds()
                    if gap > MERGE_TIME_WINDOW_DAYS * 86400.0:
                        windows.append((cid, tier, cur))
                        cur = []
                if not cur:
                    anchor = dt
                cur.append(it)
            if cur:
                windows.append((cid, tier, cur))
        return windows

    def _merge_rough_groups(self, rows: Sequence[Dict[str, Any]]
                            ) -> List[List[Dict[str, Any]]]:
        """粗筛第二步：窗口内两两 difflib 比对 + 并查集聚合。

        产出上限 ``MERGE_MAX_CANDIDATES``（50 组），每组上限
        ``MERGE_MAX_GROUP_SIZE``（5 条），少于 ``MERGE_MIN_GROUP_SIZE``
        （2 条）不成组。**这里只做粗筛，能不能合由 LLM 终审决定。**
        """
        groups: List[List[Dict[str, Any]]] = []
        for cid, tier, win in self._merge_window_groups(rows):
            if len(win) < MERGE_MIN_GROUP_SIZE:
                continue
            n = len(win)
            parent = list(range(n))

            def _find(i: int) -> int:
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i

            for i in range(n):
                for j in range(i + 1, n):
                    sim = self._merge_ratio(win[i].get("content"),
                                            win[j].get("content"))
                    if sim < SIMILAR_THRESHOLD:
                        continue
                    ri, rj = _find(i), _find(j)
                    if ri == rj:
                        continue
                    parent[max(ri, rj)] = min(ri, rj)
                    self.logger.info(
                        "[合并] 粗筛命中 owner=%s tier=%s 相似度=%.3f：%r <> %r",
                        cid, tier, sim,
                        self._merge_text(win[i].get("content"))[:40],
                        self._merge_text(win[j].get("content"))[:40])

            clusters: Dict[int, List[Dict[str, Any]]] = {}
            for i in range(n):
                clusters.setdefault(_find(i), []).append(win[i])
            for root in sorted(clusters):
                members = clusters[root]
                if len(members) < MERGE_MIN_GROUP_SIZE:
                    continue
                if len(members) > MERGE_MAX_GROUP_SIZE:
                    self.logger.info(
                        "[合并] owner=%s tier=%s 组内 %d 条超过上限 %d，本轮只取前 %d 条",
                        cid, tier, len(members), MERGE_MAX_GROUP_SIZE,
                        MERGE_MAX_GROUP_SIZE)
                    members = members[:MERGE_MAX_GROUP_SIZE]
                groups.append(members)
                if len(groups) >= MERGE_MAX_CANDIDATES:
                    self.logger.info("[合并] 候选组已达上限 %d，本轮不再产出候选",
                                     MERGE_MAX_CANDIDATES)
                    return groups
        return groups

    def _merge_llm_verdict(self, rows: Sequence[Dict[str, Any]]) -> Optional[str]:
        """LLM 终审一组粗筛候选：允许合并返回摘要，其余一律返回 None。

        提示词里的三条硬规则（brief 指定，原文照写）：

        1. 禁止补充不存在的事实
        2. 一旦有事实冲突立刻放弃合并
        3. 无法确定则放弃

        **LLM 未启用 / 报错 / 拒绝 / 摘要为空 —— 一律放弃本组**，
        绝不退化成「拼接原文」兜底（那正是把冲突记忆合成谎话的路径）。
        """
        if self.llm is None or not getattr(self.llm, "enabled", False):
            self.logger.info("[合并] LLM 未启用，本组放弃（禁止拼接兜底）")
            return None
        body = "\n".join(
            "%d. %s" % (i + 1, self._merge_text(r.get("content"),
                                                MERGE_VERDICT_TRUNCATE_LEN))
            for i, r in enumerate(rows))
        system = (
            "你是记忆合并审查员。下面列出的候选记忆都属于同一个角色，"
            "它们可能只是同一条事实的不同说法，也可能互相矛盾。\n"
            "硬性规则：\n"
            "1. 禁止补充不存在的事实：摘要只能包含候选原文已有的信息；\n"
            "2. 一旦有事实冲突（例如「知道某件事」与「不知道某件事」、"
            "「住在某地」与「不知道住哪」）立刻放弃合并；\n"
            "3. 无法确定是否同一条事实时，放弃合并；\n"
            "4. 只有确认是同一条事实的重复 / 补充表述时，才允许合并。\n"
            "只输出 JSON，不要任何多余文字：\n"
            "允许合并 -> {\"merge\": true, \"summary\": \"合并后的一句话摘要\"}\n"
            "放弃合并 -> {\"merge\": false, \"reason\": \"放弃的原因\"}"
        )
        user = "候选记忆（共 %d 条）：\n%s" % (len(rows), body)
        try:
            data = self.llm.chat_json(system, user)
        except Exception as ex:
            self.logger.warning("[合并] LLM 终审异常，本组放弃：%s", ex)
            return None
        if not isinstance(data, dict):
            self.logger.warning("[合并] LLM 终审无结果 / 不是 JSON 对象，本组放弃")
            return None
        if not bool(data.get("merge")):
            self.logger.info("[合并] LLM 拒绝合并，本组放弃：%s",
                             str(data.get("reason") or "")[:160])
            return None
        summary = str(data.get("summary") or "").strip()
        if not summary:
            self.logger.warning("[合并] LLM 同意合并但 summary 为空，本组放弃")
            return None
        return summary[:CONSOLIDATE_SUMMARY_MAX_LEN]

    def _merge_write_group(self, rows: Sequence[Dict[str, Any]],
                           summary: str) -> Optional[int]:
        """把一组记忆写成一条新记忆，并把旧记忆降级（**绝不删除**）。

        * 新记忆：**全新 ID**，``tier`` 不变，``strength = max(组内)``，
          ``emotional_residue = avg(组内)``，
          ``consolidation = max(avg, max × MERGE_CONSOLIDATION_RATIO)``，
          ``merged_from`` = 旧 ID 列表
        * 旧记忆：**ID 不变**，只把 ``status`` 改成 ``MERGE_OLD_STATUS``（weakened）
        * 整个写入是一个短事务（``BEGIN IMMEDIATE``），提交后立刻 ``close()``
        """
        ids = [int(x) for x in (_to_int(r.get("memory_id")) for r in rows)
               if x is not None]
        if len(ids) < MERGE_MIN_GROUP_SIZE:
            return None
        cid = _to_int(rows[0].get("owner_character_id"))
        if cid is None:
            return None
        tier = _to_int(rows[0].get("tier"))
        if tier not in VALID_TIERS:
            tier = DEFAULT_TIER

        strengths = [_clamp(r.get("recall_strength"), 0.0, 1.0,
                            DEFAULT_RECALL_STRENGTH) for r in rows]
        residues = [_clamp(r.get("emotional_residue"), 0.0, 1.0, 0.0)
                    for r in rows]
        cons = [_clamp(r.get("consolidation"), 0.0, CONSOLIDATION_MAX,
                       DEFAULT_CONSOLIDATION) for r in rows]
        new_strength = max(strengths) if strengths else DEFAULT_RECALL_STRENGTH
        avg_residue = sum(residues) / len(residues) if residues else 0.0
        avg_cons = sum(cons) / len(cons) if cons else DEFAULT_CONSOLIDATION
        max_cons = max(cons) if cons else DEFAULT_CONSOLIDATION
        new_cons = max(avg_cons, max_cons * MERGE_CONSOLIDATION_RATIO)

        # memory_type：取组内出现最多的那个（平票取字典序小的，可复现）
        tally: Dict[str, int] = {}
        for r in rows:
            mt = str(r.get("memory_type") or DEFAULT_MEMORY_TYPE).strip().lower()
            tally[mt] = tally.get(mt, 0) + 1
        new_type = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        if new_type not in VALID_MEMORY_TYPES:
            new_type = DEFAULT_MEMORY_TYPE

        ev_ids = [_to_int(r.get("source_event_id")) for r in rows]
        ev_ids = [e for e in ev_ids if e is not None]
        marks = ", ".join("?" * len(ids))

        with self.db.transaction():
            new_id = self.mem_mgr.add_memory(
                source_type=_inherit_source_type(rows),
                owner=cid,
                content=summary,
                memory_type=new_type,
                importance=max((_clamp(r.get("importance"), 0.0, 1.0,
                                       DEFAULT_IMPORTANCE) for r in rows),
                               default=DEFAULT_IMPORTANCE),
                confidence=(sum(_clamp(r.get("confidence"), 0.0, 1.0,
                                       DEFAULT_CONFIDENCE) for r in rows)
                            / len(rows)),
                emotional_intensity=max(
                    (_clamp(r.get("emotional_intensity"), 0.0, 1.0,
                            DEFAULT_EMOTIONAL_INTENSITY) for r in rows),
                    default=DEFAULT_EMOTIONAL_INTENSITY),
                source_event_id=(ev_ids[0] if ev_ids else None),
                is_subjective=True,
                # [防二次摘要] 合并摘要按「已压缩」落库：consolidate() 的候选
                # SQL 有 is_consolidated = 0 硬过滤，因此它不会再被当原始记忆
                # 二次压榨（只有显式 allow_nested / --mode deep 才碰它）。
                is_consolidated=True,
                tags=[MERGE_TAG],
                dedup=False,
                auto_create_event=False,
                status=MERGE_NEW_STATUS,
                tier=tier,
                emotional_residue=avg_residue,
                consolidation=new_cons,
                merged_from=ids,
            )
            if new_id is None:
                raise RuntimeError("新记忆写入失败（容量上限 / 校验拒绝）")
            cur = self.db.execute(
                "UPDATE memories SET recall_strength = ? WHERE memory_id = ?",
                (new_strength, int(new_id)))
            if cur is None:
                raise RuntimeError("新记忆 strength 回写失败")
            cur = self.db.execute(
                f"UPDATE memories SET status = ? WHERE memory_id IN ({marks})",
                tuple([MERGE_OLD_STATUS] + ids))
            if cur is None:
                raise RuntimeError("旧记忆降级失败")
        self.db.close()      # 短事务提交完立刻断开
        self.logger.info(
            "[合并] owner=%s tier=%s %d 条 -> 新记忆 id=%s"
            "（strength=%.3f 情感残留=%.3f 巩固度=%.3f，旧 id=%s 已置 %s）",
            cid, tier, len(ids), new_id, new_strength, avg_residue, new_cons,
            ids, MERGE_OLD_STATUS)
        return int(new_id)

    def merge_similar_memories(self, manual_trigger: bool = False,
                               already_locked: bool = False,
                               skip_tier1_protection: bool = True
                               ) -> Dict[str, Any]:
        """[V6 阶段D] 安全聚合合并（一次一轮，进程内互斥）。

        流程：读取 -> **立刻断开连接** -> 粗筛（difflib）-> LLM 终审 ->
        短事务写库（``BEGIN IMMEDIATE``）-> 提交后 ``close()``。

        * ``already_locked=True``：调用方（Web 后台线程）已经抢到
          ``_merge_running``，这里**不再抢锁**，但 ``finally`` 里照样释放。
        * 抢不到锁时**直接跳过**（返回 ``skipped=1``），**不碰**别人的标志位。
        * 无论成功、失败、异常，``finally`` 都把 ``_merge_running = False``
          复位 —— 这是防死锁的唯一保证。
        * **tier1 保护（两层语义已解耦）**：
          自动轮（``manual_trigger=False``）**永远**跳过 tier1 核心记忆，
          不受 ``skip_tier1_protection`` 影响；
          手动轮（``manual_trigger=True``）默认允许处理 tier1，
          若调用方仍想保护 tier1（例如「只是想标一下来源」），
          显式传 ``skip_tier1_protection=False`` 即可。
          判定式：``保护生效 = (not manual_trigger) or (not skip_tier1_protection)``
        """
        global _merge_running, _merge_last_result, _merge_last_at
        t0 = time.time()
        out: Dict[str, Any] = {
            "scanned": 0, "groups": 0, "merged": 0, "new_ids": [],
            "skipped": 0, "manual": bool(manual_trigger),
            "started_at": now_iso(), "finished_at": "", "duration_ms": 0,
        }

        if not already_locked:
            with _merge_lock:
                if _merge_running:
                    self.logger.info(
                        "[合并] 已有一轮在跑，本次跳过（manual=%s）", manual_trigger)
                    out["skipped"] = 1
                    out["reason"] = "busy"
                    out["finished_at"] = now_iso()
                    out["duration_ms"] = int((time.time() - t0) * 1000)
                    return out
                _merge_running = True

        try:
            # ---- 1. 读取（读完立刻断开连接，粗筛 / LLM 期间不占连接）----
            # [tier1 保护] 自动轮（manual_trigger=False）**永远**跳过 tier1 核心
            #              记忆（身份 / 核心关系 / 不可逆事件）；手动轮默认允许
            #              处理 tier1，除非显式传 skip_tier1_protection=False。
            _protect_tier1 = (not manual_trigger) or (not skip_tier1_protection)
            _sql = ("SELECT memory_id, owner_character_id, memory_type, content, "
                    "       importance, confidence, emotional_intensity, "
                    "       recall_strength, created_at, source_event_id, "
                    "       tier, emotional_residue, consolidation "
                    "FROM memories WHERE status = ?")
            _params: List[Any] = [MEM_STATUS_ACTIVE]
            if _protect_tier1:
                _sql += " AND tier <> ?"
                _params.append(TIER_CORE)
            _sql += " ORDER BY created_at ASC LIMIT ?"
            _params.append(MERGE_MAX_PER_RUN)
            rows = self.db.query(_sql, tuple(_params))
            try:
                self.db.close()
            except Exception as ex:
                self.logger.warning("[合并] 读后断连失败（继续）：%s", ex)
            out["scanned"] = len(rows)
            if len(rows) < MERGE_MIN_GROUP_SIZE:
                self.logger.info("[合并] 可扫描记忆不足 %d 条，本轮无需合并",
                                 MERGE_MIN_GROUP_SIZE)
                return out

            # ---- 2. 粗筛 ----
            groups = self._merge_rough_groups(rows)
            out["groups"] = len(groups)
            if not groups:
                self.logger.info("[合并] 粗筛没有产出候选组（扫描 %d 条）",
                                 len(rows))
                return out

            # ---- 3. 终审 + 写库（逐组，单组失败不影响其他组）----
            for grp in groups:
                try:
                    summary = self._merge_llm_verdict(grp)
                    if not summary:
                        continue
                    new_id = self._merge_write_group(grp, summary)
                except Exception as ex:
                    self.logger.warning(
                        "[合并] 本组写入失败，已回滚并跳过：%s", ex)
                    continue
                if new_id:
                    out["merged"] += 1
                    out["new_ids"].append(int(new_id))
        except Exception as ex:
            self.logger.exception("[合并] 本轮异常（已忽略）：%s", ex)
            out["error"] = "%s: %s" % (type(ex).__name__, ex)
        finally:
            out["finished_at"] = now_iso()
            out["duration_ms"] = int((time.time() - t0) * 1000)
            _merge_last_result = dict(out)
            _merge_last_at = out["finished_at"]
            _merge_running = False          # 防死锁：无论成败都放锁
            try:
                self.db.close()
            except Exception:
                pass

        self.logger.info(
            "[合并] 结束（%s）：扫描 %d 条 / 候选 %d 组 / 成功合并 %d 组，用时 %d ms",
            "手动" if manual_trigger else "自动", out["scanned"],
            out["groups"], out["merged"], out["duration_ms"])
        return out

    # ------------------------------------------------------------------
    # [V6 阶段D] 自动合并调度器（threading.Timer，每 MERGE_INTERVAL_MIN 分钟）
    # ------------------------------------------------------------------
    def start_merge_scheduler(self) -> bool:
        """挂上后台合并调度器；已经挂过就不重复挂（返回 False）。

        * 受模块级 ``_scheduler_lock`` 保护，全局只允许一个 Timer；
          当前 Timer 存进模块级 ``_merge_timer``，防止重复启动。
        * Timer 线程是 **daemon**：进程退出（Ctrl+C）不会被它拖住，
          所以 ``close()`` / ``serve_forever()`` 不需要改动。
        """
        global _merge_timer
        with _scheduler_lock:
            if _merge_timer is not None:
                self.logger.info("[合并] 调度器已在运行，不重复启动")
                return False
            interval_min = _to_int(
                getattr(self.config.memory, "merge_interval_min", None))
            if interval_min is None or interval_min <= 0:
                interval_min = MERGE_INTERVAL_MIN
            self._merge_interval_sec = float(interval_min) * 60.0
            self._schedule_next_merge(self._merge_interval_sec)
        self.logger.info(
            "[合并] 调度器已启动：每 %.0f 分钟自动跑一轮（auto_merge=%s）",
            self._merge_interval_sec,
            bool(getattr(self.config.memory, "auto_merge", True)))
        return True

    def _schedule_next_merge(self, interval: float) -> None:
        """内部：创建并启动下一个 Timer（调用方必须持 ``_scheduler_lock``）。"""
        global _merge_timer
        timer = threading.Timer(float(interval), self._merge_tick)
        timer.daemon = True        # 不阻塞进程退出，Ctrl+C 能干净收场
        timer.name = MERGE_THREAD_NAME
        _merge_timer = timer
        timer.start()

    def _merge_tick(self) -> None:
        """内部：一轮自动合并 + 重新安排下一轮。**绝不抛异常。**"""
        try:
            if bool(getattr(self.config.memory, "merge_enabled", True)):
                self.merge_similar_memories(manual_trigger=False)
            else:
                self.logger.info("[合并] merge_enabled=false，本轮跳过")
            # [IDF/P3] 顺手重建 df 缓存。独立 try：失败也绝不影响下面的 Timer 续期
            try:
                self.mem_mgr.build_df_cache()
            except Exception as ex:
                self.logger.warning("[IDF] df 缓存重建失败（已忽略）：%s", ex)

            # [decay] 跟合并同一节奏顺带跑一轮记忆衰减（指数衰减，绝不删除记忆）
            try:
                n = self.apply_decay()
                if n:
                    self.logger.info("[合并] 顺带衰减 %d 条记忆", n)
            except Exception as ex:
                self.logger.warning("[合并] 衰减失败（已忽略）：%s", ex)
        except Exception as ex:
            self.logger.exception("[合并] 自动调度本轮失败（已忽略）：%s", ex)
        finally:
            try:
                with _scheduler_lock:
                    if _merge_timer is not None:      # 没被 stop 取消才续期
                        self._schedule_next_merge(
                            float(getattr(self, "_merge_interval_sec",
                                          MERGE_INTERVAL_MIN * 60.0)))
            except Exception as ex:
                self.logger.warning("[合并] 调度器续期失败（已忽略）：%s", ex)

    def stop_merge_scheduler(self) -> bool:
        """取消后台调度器（测试 / 排障用）；没有在跑返回 False。"""
        global _merge_timer
        with _scheduler_lock:
            timer = _merge_timer
            _merge_timer = None
        if timer is None:
            return False
        try:
            timer.cancel()
        except Exception as ex:
            self.logger.warning("[合并] 取消失败（已忽略）：%s", ex)
        self.logger.info("[合并] 调度器已停止")
        return True

    def merge_status(self) -> Dict[str, Any]:
        """合并状态快照（只读，Web 前端轮询用；不落库）。"""
        interval_min = _to_int(
            getattr(self.config.memory, "merge_interval_min", None))
        return {
            "running": bool(_merge_running),
            "last_at": _merge_last_at,
            "last_result": dict(_merge_last_result),
            "scheduler": _merge_timer is not None,
            "interval_min": (interval_min if interval_min else
                             MERGE_INTERVAL_MIN),
        }

    def __repr__(self) -> str:
        return ("<MemoryEngine db=%r chars=%d mems=%d llm=%s>"
                % (self.config.db_path, self.char_mgr.count(),
                   self.mem_mgr.count(), "on" if self.llm.enabled else "off"))


# ==============================================================================
# 25. WebServer —— 手机可用的记忆控制台（纯标准库 http.server）
# ==============================================================================

# 批 5 追加：Web 层需要的两个标准库模块（就地导入，不改动文件头）
import http.server as _http_server  # noqa: E402
import urllib.parse as _urlparse  # noqa: E402


# ------------------------------------------------------------------------------
# 内嵌前端（无外部 CDN、无框架；蓝色卡片控制台，手机响应式）
# ------------------------------------------------------------------------------
SETTINGS_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>设置 · memory_full</title>
<style>
body{font-family:sans-serif;max-width:640px;margin:20px auto;padding:0 16px;background:#f5f5f5;color:#222}
h1{font-size:20px}
label{display:block;margin:12px 0 4px;font-size:14px;color:#555}
input{width:100%;padding:10px;font-size:15px;border:1px solid #ccc;border-radius:6px;box-sizing:border-box;background:#fff}
button{margin-top:20px;padding:12px 24px;font-size:15px;border:none;border-radius:6px;background:#4a6fa5;color:#fff;cursor:pointer}
button:active{background:#3a5a8a}
#msg{margin-top:12px;font-size:14px}
.ok{color:#2a7;}.err{color:#c33}
a{color:#4a6fa5}
</style>
</head>
<body>
<h1>设置</h1>
<p style="color:#666;font-size:13px">改完点保存 → 立即生效，不用重启。<a href="/">返回控制台</a></p>
<p style="color:#c33;font-size:12px">注意：host / port / db_path 三项改完必须重启才生效。</p>

<label>API Key（留空或显示 **** 时不修改）</label>
<input id="api_key" type="text" placeholder="sk-...">

<label>Base URL</label>
<input id="base_url" type="text">

<label>模型名</label>
<input id="model" type="text">

<label>Max Tokens（抽取用）</label>
<input id="max_tokens" type="number">

<label>温度</label>
<input id="temperature" type="number" step="0.1" min="0" max="2">

<label>默认角色（中继没传 ?char= 时用，可空）</label>
<input id="default_character" type="text">

<label>默认卡（可空）</label>
<input id="default_card" type="text">

<label>用户真名（多个用英文逗号分隔）</label>
<input id="user_names" type="text" placeholder="User,明,用户,玩家">

<label>LLM 启用</label>
<input id="llm_enabled" type="text" placeholder="true / false">

<button onclick="save()">保存</button>
<div id="msg"></div>

<script>
async function load(){
  const r = await fetch('/api/settings');
  const j = await r.json();
  if(!j.ok){document.getElementById('msg').textContent = '读取失败：'+j.err; return;}
  const c = j.config, L = c.llm || {}, M = c.memory || {};
  api_key.value = L.api_key || '';
  base_url.value = L.base_url || '';
  model.value = L.model || '';
  max_tokens.value = L.max_tokens || '';
  temperature.value = L.temperature || '';
  default_character.value = L.default_character || '';
  default_card.value = L.default_card || '';
  llm_enabled.value = L.enabled ? 'true' : 'false';
  user_names.value = (M.user_names || []).join(',');
}
async function save(){
  const body = {
    llm: {
      api_key: api_key.value.trim(),
      base_url: base_url.value.trim(),
      model: model.value.trim(),
      max_tokens: parseInt(max_tokens.value) || undefined,
      temperature: parseFloat(temperature.value) || undefined,
      default_character: default_character.value.trim(),
      default_card: default_card.value.trim(),
      enabled: llm_enabled.value.trim() === 'true',
    },
    memory: {
      user_names: user_names.value.split(',').map(s=>s.trim()).filter(Boolean),
    }
  };
  const r = await fetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j = await r.json();
  const msg = document.getElementById('msg');
  if(j.ok){msg.className='ok'; msg.textContent='已保存并生效';}
  else{msg.className='err'; msg.textContent='保存失败：'+(j.err||'unknown');}
}
load();
</script>
</body>
</html>
"""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light">
<title>记忆控制台 · memory_full</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{
--blue:#1a73e8;--blue-dark:#0b47a1;--blue-soft:#e8f0fe;--blue-mid:#c3d7f7;
--bg:#eef3fa;--card:#ffffff;--ink:#16233a;--muted:#6b7a90;
--line:#dbe6f6;--ok:#1e8e3e;--warn:#b26a00;--bad:#c5221f;
--r:14px;--sh:0 1px 3px rgba(16,42,84,.08),0 6px 18px rgba(16,42,84,.06)}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;-webkit-text-size-adjust:100%}
a{color:inherit;text-decoration:none}
.wrap{width:100%;max-width:960px;margin:0 auto;padding:0 14px}
.top{position:sticky;top:0;z-index:20;background:linear-gradient(135deg,var(--blue-dark),var(--blue));color:#fff;box-shadow:0 2px 12px rgba(11,71,161,.28)}
.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:10px;height:58px}
.brand{display:flex;align-items:center;gap:9px;font-size:17px;font-weight:600;letter-spacing:.3px}
.dot{width:10px;height:10px;border-radius:50%;background:#8cf0b0;box-shadow:0 0 0 4px rgba(140,240,176,.22)}
.btn{border:0;background:rgba(255,255,255,.18);color:#fff;font:inherit;font-size:14px;padding:7px 14px;border-radius:20px;cursor:pointer}
.btn:active{background:rgba(255,255,255,.32)}
main{padding:16px 0 40px;min-height:60vh}
.foot{color:var(--muted);font-size:12.5px;text-align:center;padding:10px 14px 28px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(84px,1fr));gap:8px;margin-bottom:16px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:9px 10px;text-align:center;box-shadow:var(--sh)}
.chip span{display:block;color:var(--muted);font-size:11.5px;letter-spacing:.4px}
.chip b{display:block;font-size:19px;margin-top:2px;color:var(--blue-dark);font-variant-numeric:tabular-nums}
.chip.tap{cursor:pointer;border-color:var(--blue-mid);background:linear-gradient(180deg,#fff,#f2f7ff)}
.chip.tap b{color:var(--blue)}
.chip.tap:active{transform:scale(.97)}
.chip.tap span:after{content:" ›";color:var(--blue-mid);font-weight:700}
.chip.off b{color:var(--muted);opacity:.55}
.sheetmask{position:fixed;left:0;right:0;top:0;bottom:0;background:rgba(10,22,42,.45);z-index:60;display:flex;align-items:flex-end;justify-content:center;padding:0}
.sheet{width:100%;max-width:960px;min-width:0;box-sizing:border-box;background:var(--card);border-radius:18px 18px 0 0;max-height:86vh;display:flex;flex-direction:column;box-shadow:0 -10px 34px rgba(11,71,161,.28);animation:sheetup .18s ease-out}
@keyframes sheetup{from{transform:translateY(22px);opacity:.5}to{transform:translateY(0);opacity:1}}
.sheethd{display:flex;align-items:center;gap:10px;justify-content:space-between;padding:13px 16px;border-bottom:1px solid var(--line);min-width:0}
.sheetttl{font-size:16px;font-weight:700;min-width:0;overflow-wrap:anywhere}
.sheetttl small{display:block;margin-top:2px;color:var(--muted);font-size:12px;font-weight:400}
.sheetx{border:0;background:var(--blue-soft);color:var(--blue-dark);font:inherit;font-size:14px;font-weight:600;border-radius:20px;padding:7px 15px;cursor:pointer;white-space:nowrap;flex:0 0 auto}
.sheetbd{overflow:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch;padding:12px 14px 24px;min-width:0}
.srow{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--blue-mid);border-radius:12px;padding:10px 12px;margin-bottom:9px;min-width:0}
.srow .h{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-bottom:5px;min-width:0}
.srow .t{margin:0;font-size:14.5px;color:var(--ink);white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere}
.srow .m{margin-top:6px;font-size:12px;color:var(--muted);overflow-wrap:anywhere}
.secttl{font-size:13px;font-weight:700;color:var(--muted);letter-spacing:1.2px;margin:18px 2px 9px}
.clist{display:grid;grid-template-columns:1fr;gap:10px}
@media(min-width:620px){.clist{grid-template-columns:1fr 1fr}}
.char{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:var(--r);padding:12px 14px;box-shadow:var(--sh);transition:transform .12s ease}
.char:active{transform:scale(.985)}
.avatar{flex:0 0 44px;width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,var(--blue),var(--blue-dark));color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:600}
.avatar.u{background:linear-gradient(135deg,#f5a623,#e2760a)}
.cmeta{min-width:0;flex:1}
.cname{display:flex;align-items:center;gap:7px;font-weight:600;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{color:var(--muted);font-size:12.5px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badge{font-size:11px;font-weight:600;padding:2px 8px;border-radius:20px;background:var(--blue-soft);color:var(--blue-dark);border:1px solid var(--blue-mid)}
.badge.main_character{background:#e6f4ea;color:#137333;border-color:#b7e1c3}
.badge.npc{background:#fef7e0;color:#956f00;border-color:#fae3a1}
.badge.user{background:#fce8e6;color:#b3261e;border-color:#f7c8c3}
.badge.system{background:#eceff3;color:#5f6368;border-color:#d6dbe1}
.chev{color:var(--blue-mid);font-size:22px;line-height:1;padding-left:2px}
/* V3 追加：一级「卡牌」卡 —— 比二级「角色」卡更大，视觉上分层 */
.klist{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:620px){.klist{grid-template-columns:1fr 1fr}}
.kcard{display:flex;align-items:center;gap:14px;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--blue);border-radius:var(--r);padding:18px 16px;box-shadow:var(--sh);transition:transform .12s ease}
.kcard:active{transform:scale(.985)}
.kico{flex:0 0 54px;width:54px;height:54px;border-radius:14px;background:linear-gradient(135deg,var(--blue-soft),var(--blue-mid));display:flex;align-items:center;justify-content:center;font-size:26px;line-height:1}
.kname{font-weight:700;font-size:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:7px}
.km{font-variant-numeric:tabular-nums}
.back{display:inline-flex;align-items:center;gap:6px;color:var(--blue-dark);font-size:14px;font-weight:600;margin:2px 0 12px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:6px 14px}
.head{margin:0 0 12px}
.head h1{margin:0;font-size:22px;letter-spacing:.3px}
.head .sub{margin-top:5px}
.searchbar{margin:0 0 14px}
.searchbar input{width:100%;font:inherit;font-size:15px;padding:11px 14px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);outline:none}
.searchbar input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(26,115,232,.14)}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--blue-mid);border-radius:var(--r);padding:13px 15px;margin-bottom:11px;box-shadow:var(--sh)}
.crow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.mt{font-size:11.5px;font-weight:700;letter-spacing:.5px;padding:3px 9px;border-radius:20px;background:var(--blue-soft);color:var(--blue-dark);border:1px solid var(--blue-mid)}
.st{font-size:11px;padding:2px 8px;border-radius:20px;background:#f1f4f8;color:var(--muted);border:1px solid var(--line)}
.st-active{background:#e6f4ea;color:#137333;border-color:#b7e1c3}
.st-reinforced{background:#e8f0fe;color:var(--blue-dark);border-color:var(--blue-mid)}
.st-weakened{background:#fff4e5;color:var(--warn);border-color:#ffe0b2}
.st-superseded,.st-contradicted{background:#fce8e6;color:var(--bad);border-color:#f7c8c3}
.score{margin-left:auto;font-size:12px;color:var(--blue-dark);font-weight:600;background:var(--blue-soft);border-radius:20px;padding:3px 10px}
.body{margin:0;white-space:pre-wrap;word-break:break-word;font-size:14.6px}
.foot-row,.foot{margin-top:9px;color:var(--muted);font-size:12px}
.t{color:var(--blue);margin-left:5px}
.loading,.empty,.err{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:22px;text-align:center;color:var(--muted)}
.err{color:var(--bad);border-color:#f7c8c3;background:#fff7f6}
/* [V6 阶段D] 手动整理记忆按钮 */
.mergebar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 14px}
.mbtn{border:1px solid var(--blue-mid);background:var(--blue-soft);color:var(--blue-dark);font:inherit;font-size:14px;font-weight:600;padding:8px 15px;border-radius:20px;cursor:pointer;box-shadow:var(--sh)}
.mbtn:active{transform:scale(.97)}
.mbtn:disabled{opacity:.55;cursor:default;transform:none}
.mstat{font-size:12.5px;color:var(--muted)}
.mstat.ok{color:#137333}
.mstat.bad{color:var(--bad)}
/* [手动记忆] 手动新增 / 编辑 / 归档（纯原生样式，移动端优先） */
.cardacts{display:inline-flex;gap:6px;margin-left:auto;flex-wrap:wrap}
/* 窄屏（手机）下让操作按钮独占一行靠右，避免被挤出记忆卡片 */
@media(max-width:520px){
  .crow .cardacts{margin-left:0;flex-basis:100%;justify-content:flex-end}
}
/* 窄屏：长中文正文/脚注不再把卡片撑出屏幕
   （overflow-wrap:anywhere 会参与 min-content 计算，word-break:break-word 不会） */
.clist,.card{min-width:0}
.card .body,.card .foot-row{overflow-wrap:anywhere;word-break:break-all}
.abtn{border:1px solid var(--line);background:var(--card);color:var(--blue-dark);font:inherit;font-size:12.5px;font-weight:600;padding:6px 12px;border-radius:14px;cursor:pointer;min-height:34px}
.abtn:active{transform:scale(.96)}
.abtn-warn{color:var(--bad);border-color:#f7c8c3;background:#fff7f6}
.memform label{display:block;font-size:13px;color:var(--muted);margin:12px 0 5px;font-weight:600}
.memform textarea{width:100%;box-sizing:border-box;font:inherit;font-size:16px;line-height:1.5;padding:12px 13px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);min-height:132px;resize:vertical;outline:none}
.memform textarea:focus,.memform select:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(26,115,232,.14)}
.memform select{width:100%;box-sizing:border-box;font:inherit;font-size:16px;padding:12px 13px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);outline:none;min-height:46px}
.memform input[type=range]{width:100%;height:34px}
.memform .two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.memform .actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}
.savebtn{border:0;background:var(--blue);color:#fff;font:inherit;font-size:16px;font-weight:700;padding:14px;border-radius:14px;cursor:pointer;min-height:50px}
.savebtn:active{transform:scale(.98)}
.savebtn:disabled{opacity:.6;cursor:default;transform:none}
.cancelbtn{border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit;font-size:16px;padding:14px;border-radius:14px;cursor:pointer;min-height:50px}
.fmsg{margin-top:12px;font-size:13.5px;min-height:18px}
.fmsg.ok{color:#137333}
.fmsg.bad{color:var(--bad)}
@media(max-width:420px){.memform .two{grid-template-columns:1fr}}
@media(max-width:520px){.char{gap:8px;padding:10px 11px}.char .abtn{font-size:12px;padding:6px 9px;margin-right:2px}.char .avatar{flex:0 0 36px;width:36px;height:36px;font-size:17px}}
/* [卡片逻辑删除] 删除按钮 + 已删除卡片恢复区 */
.mbtn-danger{border-color:#f7c8c3;background:#fff7f6;color:var(--bad)}
.char{min-width:0}
.char .cname,.char .sub{min-width:0;overflow-wrap:anywhere;word-break:break-all}
.char>.abtn{flex:0 0 auto;white-space:nowrap;margin-right:6px;text-decoration:none}
.abtn.danger{color:#c5221f;border-color:#f0bdb8;background:#fff6f5}
.abtn.danger:hover{background:#fdecea}
.addbtn{font-size:12.5px;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--blue);font-weight:700;cursor:pointer;margin-left:8px;white-space:nowrap}
.addbtn:active{transform:scale(.97)}
.aliasline{font-size:12px;color:var(--muted);margin-top:2px;overflow-wrap:anywhere;word-break:break-all}
.warnbox{margin:14px 0;padding:11px 13px;border-radius:14px;background:#fff8e6;border:1px solid #f0d9a0;color:#8a5a00;font-size:13px;line-height:1.62;overflow-wrap:anywhere;word-break:break-all}
.delbox{margin:18px 0 0}
.delbox summary{cursor:pointer;font-size:13px;color:var(--muted);padding:8px 2px;list-style:none}
.delbox summary::-webkit-details-marker{display:none}
.delbox summary::before{content:'▸ '}
.delbox[open] summary::before{content:'▾ '}
/* ===== [页面内弹窗] 替代 alert()/confirm()：纯原生 Modal + Toast，零第三方、不阻塞渲染 ===== */
.uimask{position:fixed;left:0;right:0;top:0;bottom:0;background:rgba(10,22,42,.5);z-index:90;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box}
.uimod{width:100%;max-width:420px;min-width:0;box-sizing:border-box;background:var(--card);border-radius:18px;overflow:hidden;box-shadow:0 12px 40px rgba(11,71,161,.30);animation:uipop .16s ease-out}
@keyframes uipop{from{transform:scale(.94);opacity:.45}to{transform:scale(1);opacity:1}}
.uihd{padding:16px 18px 0}
.uihd h3{margin:0;font-size:17px;font-weight:800;color:var(--ink)}
.uimod.danger .uihd h3{color:var(--bad)}
.uibd{padding:10px 18px 4px;font-size:14.5px;line-height:1.62;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-all;max-height:52vh;overflow:auto}
.uift{display:flex;gap:10px;padding:14px 18px 18px}
.uift button{flex:1}
.uift button:focus{outline:none}
.uift button:focus-visible{outline:2px solid #9dc0f0;outline-offset:2px}
.savebtn.danger{background:var(--bad)}
.uibd .uiln{margin:0 0 7px}
.uibd .uiln:last-child{margin-bottom:0}
.uibd .uigap{height:7px}
.uibd .uikv{margin-top:10px;padding:9px 11px;border-radius:12px;background:#f4f7fc;border:1px solid var(--line);font-size:13px;color:var(--muted)}
.uittoast{position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:95;max-width:88vw;box-sizing:border-box;background:rgba(17,32,58,.94);color:#fff;font-size:13.5px;line-height:1.5;padding:10px 16px;border-radius:999px;box-shadow:0 8px 22px rgba(11,71,161,.32);pointer-events:none;animation:uidrop .18s ease-out;overflow-wrap:anywhere}
.uittoast.ok{background:rgba(19,115,51,.95)}
.uittoast.bad{background:rgba(190,40,30,.95)}
@keyframes uidrop{from{transform:translate(-50%,-10px);opacity:0}to{transform:translate(-50%,0);opacity:1}}
@media(max-width:520px){.uimask{padding:14px;align-items:center}.uibd{max-height:46vh}.uift{padding:12px 14px 14px}.uihd{padding:14px 14px 0}.uibd{padding:9px 14px 2px}}
.kcard-dead{opacity:.72}
.kcard-dead .kbtn{flex:0 0 auto}
</style>
</head>
<body>
<header class="top">
  <div class="wrap">
    <div class="brand"><span class="dot"></span><b id="ttl">记忆控制台</b></div>
    <button id="refresh" class="btn" type="button">刷新</button>
  </div>
</header>
<main class="wrap" id="view"><div class="loading">载入中…</div></main>
<footer class="wrap foot">memory_full · 多角色长期记忆引擎 · 每个角色只看到自己的记忆<span id="userline"></span></footer>
<script>
'use strict';
var view = document.getElementById('view');
var ttl = document.getElementById('ttl');
var q = '';

function esc(s){
  return String(s === null || s === undefined ? '' : s)
    .replaceAll('&','&amp;').replaceAll('<','&lt;')
    .replaceAll('>','&gt;').replaceAll('"','&quot;');
}
function num(v, d){
  var n = Number(v);
  return isFinite(n) ? n : (d === undefined ? 0 : d);
}
function f2(v){ return num(v).toFixed(2); }

function get(url){
  return fetch(url, {cache:'no-store'}).then(function(r){
    return r.text().then(function(t){
      var j = null;
      try { j = JSON.parse(t); } catch (e) { throw new Error('返回不是 JSON：' + t.slice(0,120)); }
      if (!r.ok) { throw new Error((j && j.error) || ('HTTP ' + r.status)); }
      return j;
    });
  });
}
// V5.4：统计块三种样子 —— 可点(tap，带 ›) / 普通(plain) / 本轮不做(off，数字浅一点)
function chip(k, v, act, off){
  var cls = act ? 'chip tap' : (off ? 'chip off' : 'chip');
  var click = act ? (' onclick="openSheet(\'' + esc(act) + '\')"') : '';
  return '<div class="' + cls + '"' + click + '><span>' + esc(k)
    + '</span><b>' + esc(v) + '</b></div>';
}
function badge(role){
  var r = esc(role || 'unknown');
  return '<span class="badge ' + r + '">' + r + '</span>';
}

function charRow(c, withHide){
  var initial = esc((c.name || '?').slice(0,1));
  var cls = c.is_user ? 'avatar u' : 'avatar';
  var href = '#/c/' + encodeURIComponent(c.name || '');
  return '<a class="char" href="' + href + '">'
    + '<div class="' + cls + '">' + initial + '</div>'
    + '<div class="cmeta"><div class="cname">👤 ' + esc(c.name) + badge(c.role_type) + '</div>'
    + '<div class="sub">消息 ' + esc(c.message_count || 0)
    + ' · 记忆 ' + esc(c.memory_count || 0)
    + ' · 信念 ' + esc(c.belief_count || 0)
    + ' · 知识 ' + esc(c.knowledge_count || 0)
    + (c.active ? ' · 活跃' : '') + '</div>'
    + ((c.aliases && c.aliases.filter(function(a){ return a !== c.name; }).length)
        ? '<div class="aliasline">别名：'
          + esc(c.aliases.filter(function(a){ return a !== c.name; }).join('、'))
          + '</div>' : '')
    + '</div>'
    + (withHide
        ? '<button class="abtn js-hidechar" type="button" data-cid="'
          + esc(c.character_id) + '" data-cname="' + esc(c.name)
          + '">归档/隐藏</button>'
        : '')
    + '<div class="chev">›</div></a>';
}

// V5.3：底部一行小字 —— 让用户知道系统认得他，且他不参与记忆
function setUserLine(label, hidden){
  var el = document.getElementById('userline');
  if (!el){ return; }
  if (!label && !hidden){ el.textContent = ''; return; }
  var t = label ? ('当前用户：' + label) : '当前用户';
  t += hidden ? ('（用户身份已隐藏 ' + hidden + ' 个，不参与记忆）')
              : '（用户身份不参与记忆）';
  t += ' · 若开场白里写了【user】=名字，则仅以开场白为准';
  el.textContent = ' · ' + t;
}

// V3 一级：卡片列表（#/）
function renderCards(){
  ttl.textContent = '记忆控制台';
  view.innerHTML = '<div class="loading">载入卡片…</div>';
  Promise.all([
    get('/api/stats').catch(function(){ return null; }),
    get('/api/cards').catch(function(e){ return {__err:e.message}; })
  ]).then(function(res){
    var s = res[0], d = res[1];
    if (d && d.__err){
      view.innerHTML = '<div class="err">卡片读取失败：' + esc(d.__err) + '</div>';
      return;
    }
    var cards = (d && d.cards) || [];
    // V5.3：散装角色只显示 AI 扮演的角色；用户身份走 users，不显示
    var loose = ((d && d.loose) || []).filter(function(c){ return !c.is_user; });
    var users = (d && d.users) || [];
    setUserLine((d && d.current_user) || '', users.length);
    var html = '';
    if (s){
      html += '<section class="stats">'
        + chip('卡', s.cards || 0) + chip('角色', s.characters)
        + chip('消息', s.messages, 'messages')
        + chip('未处理', s.unprocessed) + chip('事件', s.events, 'events')
        + chip('可见性', s.event_visibility, 'visibility')
        + chip('记忆', s.memories, 'memories')
        + chip('信念', s.beliefs, 'beliefs') + chip('知识', s.knowledge, 'knowledge')
        + chip('关系', s.relationships, 'relationships')
        + chip('承诺', s.commitments, 'commitments')
        + chip('秘密', s.secrets, 'secrets')
        + '</section>';
    }
    html += '<div class="secttl">卡片（' + cards.length + '）'
      + '<button class="addbtn js-newcard" type="button">＋ 新建卡片</button></div>';
    if (!cards.length){
      html += '<div class="empty">还没有卡片。中继带一次卡名就会自动建卡：<br>'
        + '<code>?card=你的卡名</code> 或请求头 <code>X-Card</code></div>';
    } else {
      html += '<div class="klist">';
      cards.forEach(function(k){
        html += '<a class="kcard" href="#/card/' + encodeURIComponent(k.name || '') + '">'
          + '<div class="kico">🎴</div>'
          + '<div class="cmeta"><div class="kname">' + esc(k.name) + '</div>'
          + '<div class="sub km">角色 ' + esc(k.character_count || 0)
          + ' · 记忆 ' + esc(k.memory_count || 0)
          + (k.last_seen ? ' · 最近 ' + esc(String(k.last_seen).slice(0,16)) : '')
          + '</div></div>'
          + '<div class="chev">›</div></a>';
      });
      html += '</div>';
    }
    // [V2.2 铁律] 角色必须挂卡：控制台不再有「散装角色」区。
    // 后端自愈（引擎启动 + 新建角色时）会把无卡真实角色自动归位到「默认卡」；
    // 万一仍有漏网，这里只报警，绝不把它当成正常列表展示。
    if (loose.length){
      html += '<div class="warnbox">⚠ 发现 ' + loose.length
        + ' 个无卡角色（违反「角色必须挂卡」，应已自动归位到「默认卡」，'
        + '请刷新或重启服务；若仍出现请反馈）：'
        + esc(loose.map(function(c){ return c.name; }).join('、'))
        + '</div>';
    }
    // [卡片逻辑删除] 已删除的卡片：折叠区 + 恢复（逻辑删除，数据一行没少）
    var dead = (d && d.inactive) || [];
    if (dead.length){
      html += '<details class="delbox"><summary>已删除的卡片（' + dead.length
        + '）· 点开可恢复</summary><div class="klist">';
      dead.forEach(function(k){
        html += '<div class="kcard kcard-dead">'
          + '<div class="kico">🗑</div>'
          + '<div class="cmeta"><div class="kname">' + esc(k.name) + '</div>'
          + '<div class="sub km">角色 ' + esc(k.character_count || 0)
          + ' · 记忆 ' + esc(k.memory_count || 0)
          + ' · 已删除（数据仍在）</div></div>'
          + '<button class="abtn js-restore" type="button" data-card="'
          + esc(k.name) + '">恢复</button></div>';
      });
      html += '</div></details>';
    }
    // [角色隐藏] 已隐藏的角色（active=0）：折叠区 + 恢复
    var hid = (d && d.hidden) || [];
    if (hid.length){
      html += '<details class="delbox"><summary>已隐藏的角色（' + hid.length
        + '）· 点开可恢复</summary><div class="clist">';
      hid.forEach(function(c){
        html += '<div class="char">'
          + '<div class="avatar">' + esc((c.name || '?').slice(0,1)) + '</div>'
          + '<div class="cmeta"><div class="cname">👤 ' + esc(c.name)
          + badge(c.role_type) + '</div>'
          + '<div class="sub">消息 ' + esc(c.message_count || 0)
          + ' · 记忆 ' + esc(c.memory_count || 0)
          + ' · 已隐藏（数据仍在，' + (c.card_id ? '挂卡 ' + esc(c.card_id) : '散装')
          + '）</div></div>'
          + '<button class="abtn js-unhidechar" type="button" data-cid="'
          + esc(c.character_id) + '" data-cname="' + esc(c.name)
          + '">恢复</button>'
          // [V2.7 彻底移除] 打 purged_at 标记 → 从 UI 完全消失（行与记忆留档）
          + '<button class="abtn danger js-purgechar" type="button" data-cid="'
          + esc(c.character_id) + '" data-cname="' + esc(c.name)
          + '">彻底移除</button></div>';
      });
      html += '</div></details>';
    }
    view.innerHTML = html;
    // 恢复按钮：卡名走 data-card，不拼进 onclick（卡名可能含引号）
    Array.prototype.forEach.call(
      document.querySelectorAll('.js-restore'), function(b){
        b.addEventListener('click', function(){
          restoreCard(b.getAttribute('data-card'));
        });
      });
    // [角色隐藏] 按钮：cid/名字走 data-*，不拼进 onclick（名字可能含引号）
    Array.prototype.forEach.call(
      document.querySelectorAll('.js-newcard'), function(b){
        b.addEventListener('click', openCardCreate);
      });
    Array.prototype.forEach.call(
      document.querySelectorAll('.js-hidechar'), function(b){
        b.addEventListener('click', function(ev){
          ev.preventDefault(); ev.stopPropagation();
          hideChar(b.getAttribute('data-cid'), b.getAttribute('data-cname'));
        });
      });
    Array.prototype.forEach.call(
      document.querySelectorAll('.js-unhidechar'), function(b){
        b.addEventListener('click', function(){
          unhideChar(b.getAttribute('data-cid'), b.getAttribute('data-cname'));
        });
      });
    Array.prototype.forEach.call(
      document.querySelectorAll('.js-purgechar'), function(b){
        b.addEventListener('click', function(){
          purgeChar(b.getAttribute('data-cid'), b.getAttribute('data-cname'));
        });
      });
  });
}

// [死按钮修复] 二级页的角色按钮绑定。
// 原来这些绑定只写在 renderCards()（一级页）里，而按钮由 charRow() 产出、
// 二级页也渲染 charRow(...,true) —— 于是二级页点「隐藏/恢复/彻底移除」全无反应。
function wireCharButtons(){
  Array.prototype.forEach.call(
    document.querySelectorAll('.js-hidechar'), function(b){
      b.addEventListener('click', function(ev){
        ev.preventDefault(); ev.stopPropagation();
        hideChar(b.getAttribute('data-cid'), b.getAttribute('data-cname'));
      });
    });
  Array.prototype.forEach.call(
    document.querySelectorAll('.js-unhidechar'), function(b){
      b.addEventListener('click', function(ev){
        ev.preventDefault(); ev.stopPropagation();
        unhideChar(b.getAttribute('data-cid'), b.getAttribute('data-cname'));
      });
    });
  Array.prototype.forEach.call(
    document.querySelectorAll('.js-purgechar'), function(b){
      b.addEventListener('click', function(ev){
        ev.preventDefault(); ev.stopPropagation();
        purgeChar(b.getAttribute('data-cid'), b.getAttribute('data-cname'));
      });
    });
}

// V3 二级：卡下角色（#/card/<card_name>）
function renderCard(name){
  ttl.textContent = name;
  view.innerHTML = '<div class="loading">载入 ' + esc(name) + ' …</div>';
  get('/api/cards/' + encodeURIComponent(name) + '/characters').then(function(d){
    var k = d.card || {};
    // V5.3：卡下角色也不显示用户身份（卡是 AI 角色的容器）
    var list = (d.characters || []).filter(function(c){ return !c.is_user; });
    var html = '<a class="back" href="#/">← 返回卡片列表</a>';
    html += '<div class="head"><h1>🎴 ' + esc(k.name) + '</h1>'
      + '<div class="sub">角色 ' + esc(list.length)
      + ' · 记忆 ' + esc(k.memory_count || 0)
      + (k.last_seen ? ' · 最近活跃 ' + esc(String(k.last_seen).slice(0,16)) : '')
      + '</div>'
      + ((k.aliases && k.aliases.filter(function(a){ return a !== k.name; }).length)
         ? '<div class="aliasline">卡片别名：'
           + esc(k.aliases.filter(function(a){ return a !== k.name; }).join('、'))
           + '</div>' : '')
      + '</div>';
    html += mergeBoxHtml();      // [V6 阶段D] 手动整理当前卡记忆
    // [卡片逻辑删除] 删除这张卡：只改 is_active + 解绑角色，绝不删数据
    html += '<div class="mergebar">'
      + '<button id="delcardbtn" class="mbtn mbtn-danger" type="button">'
      + '🗑 彻底删除这张卡（卡 + 角色 + 全部记忆）</button>'
      + '<span id="delcardstat" class="mstat"></span></div>';
    html += '<div class="secttl">角色（' + list.length + '）'
      + '<button class="addbtn js-newchar" type="button" data-card="'
      + esc(k.name) + '">＋ 添加角色</button></div>';
    if (!list.length){
      html += '<div class="empty">这张卡下还没有角色</div>';
    } else {
      html += '<div class="clist">';
      list.forEach(function(c){ html += charRow(c, true); });
      html += '</div>';
    }
    // [角色隐藏修复] 已隐藏的角色（active=0）：二级页也给折叠区 + 恢复，
    // 不然角色在这张卡里就「看不见也回不来」（数据其实一直在）。
    var hid = (d.hidden_characters || []).filter(function(c){
      return !c.is_user; });
    if (hid.length){
      html += '<details class="delbox"><summary>已隐藏的角色（'
        + hid.length + '）· 点开可恢复</summary><div class="clist">';
      hid.forEach(function(c){
        html += '<div class="char">'
          + '<div class="avatar">' + esc((c.name || '?').slice(0,1)) + '</div>'
          + '<div class="cmeta"><div class="cname">👤 ' + esc(c.name)
          + badge(c.role_type) + '</div>'
          + '<div class="sub">消息 ' + esc(c.message_count || 0)
          + ' · 记忆 ' + esc(c.memory_count || 0) + ' · 已隐藏</div></div>'
          + '<button class="abtn js-unhidechar" type="button" data-cid="'
          + esc(c.character_id) + '" data-cname="' + esc(c.name)
          + '">恢复</button></div>';
      });
      html += '</div></details>';
    }
    view.innerHTML = html;
    wireCharButtons();           // [死按钮修复] 二级页的角色按钮
    wireMerge();                 // [V6 阶段D] 绑按钮 + 接上正在跑的轮询
    var delBtn = document.getElementById('delcardbtn');
    if (delBtn){
      delBtn.addEventListener('click', function(){ purgeCardAll(k.name); });
    }
    Array.prototype.forEach.call(
      document.querySelectorAll('.js-newchar'), function(b){
        b.addEventListener('click', function(){
          openCharCreate(b.getAttribute('data-card'));
        });
      });
  }).catch(function(e){
    view.innerHTML = '<a class="back" href="#/">← 返回卡片列表</a>'
      + '<div class="err">' + esc(e.message) + '</div>';
  });
}

function cardHtml(m){
  var tags = (m.tags || []).map(function(t){ return '<span class="t">#' + esc(t) + '</span>'; }).join('');
  var score = (m._score !== undefined && m._score !== null)
    ? '<span class="score">分 ' + f2(m._score) + '</span>'
    : '<span class="score">重要 ' + f2(m.importance) + '</span>';
  return '<article class="card">'
    + '<div class="crow"><span class="mt">' + esc(m.memory_type) + '</span>'
    + '<span class="st st-' + esc(m.status) + '">' + esc(m.status) + '</span>'
    + score
    + '<span class="cardacts">'
    + '<button class="abtn" type="button" onclick="openMemEdit(' + num(m.memory_id, 0) + ')">编辑</button>'
    + (String(m.status) === 'archived'
        ? '<button class="abtn" type="button" onclick="unarchiveMem(' + num(m.memory_id, 0) + ')">恢复</button>'
        : '<button class="abtn abtn-warn" type="button" onclick="archiveMem(' + num(m.memory_id, 0) + ')">归档</button>')
    + '</span>'
    + '</div>'
    + '<p class="body">' + esc(m.content) + '</p>'
    + '<div class="foot-row">强度 ' + f2(num(m.recall_strength, 1))
    + ' · 置信 ' + f2(m.confidence)
    + ' · 情绪 ' + f2(m.emotional_intensity)
    + ' · tier ' + esc(num(m.tier, 3))
    + ' · 来源 ' + esc(m.source_type || 'UNKNOWN')
    + ' · 想起 ' + esc(m.recall_count || 0) + ' 次'
    + ' · ' + esc(String(m.created_at || '').slice(0,16))
    + (tags ? ' · ' + tags : '') + '</div>'
    + '</article>';
}

function renderChar(name){
  ttl.textContent = name;
  view.innerHTML = '<div class="loading">载入 ' + esc(name) + ' …</div>';
  var url = '/api/memories/' + encodeURIComponent(name) + '?limit=100';
  if (q) { url += '&q=' + encodeURIComponent(q); }
  get(url).then(function(d){
    var c = d.character || {};
    // V3：三级页面的「← 返回」指回二级（所在卡）；散装角色才回一级
    var backCard = d.card && d.card.name ? String(d.card.name) : '';
    var backHref = backCard ? ('#/card/' + encodeURIComponent(backCard)) : '#/';
    var backText = backCard ? ('← 返回 ' + backCard) : '← 返回卡片列表';
    var html = '<a class="back" href="' + backHref + '">' + esc(backText) + '</a>';
    html += '<div class="head"><h1>' + esc(c.name) + ' ' + badge(c.role_type) + '</h1>'
      + '<div class="sub">消息 ' + esc(c.message_count || 0)
      + ' · ' + esc(d.count || 0) + ' 条记忆'
      + (d.query ? ' · 关键词「' + esc(d.query) + '」' : '') + '</div></div>';
    // [物理删除] 角色删除按钮下沉到本页（三级页面），不再出现在卡片的角色行上
    if (c.character_id !== undefined && c.character_id !== null && !c.is_user){
      html += '<div class="mergebar">'
        + '<button class="mbtn mbtn-danger js-delchar" type="button" '
        + 'onclick="event.stopPropagation();event.preventDefault();deleteChar(this.dataset.cid,this.dataset.cname);return false;" '
        + 'data-cid="' + esc(c.character_id) + '" data-cname="' + esc(c.name) + '">'
        + '🗑 永久删除这个角色（含全部记忆）</button></div>';
    }
    // [D-2 身份·性格] 手填档案 → characters.static_profile（写入后进【你是】块 + 抽取名单）
    html += '<div class="memform" id="profbox">'
      + '<label>【身份 · 性格 · 外貌】</label>'
      + '<textarea id="profid" rows="2" style="min-height:76px" placeholder="身份：例 角色D，母亲，40 岁上下"></textarea>'
      + '<textarea id="profpers" rows="2" style="min-height:76px" placeholder="性格：例 严厉、关心家人、不轻易表达"></textarea>'
      + '<textarea id="profappr" rows="2" style="min-height:76px" placeholder="外貌：例 二十出头，清秀，黑色长发"></textarea>'
      + '<textarea id="profalias" rows="2" style="min-height:76px" placeholder="别名（逗号分隔）：例 角色A、小A"></textarea>'
      + '<div class="mergebar">'
      + '<button id="saveprobtn" class="mbtn js-saveprofile" type="button">💾 保存</button>'
      + '<span id="prostat" class="mstat"></span>'
      + '</div></div>';
    // [手动记忆] 手动新增入口（移动端：大按钮）
    html += '<div class="mergebar">'
      + '<button id="addmembtn" class="mbtn" type="button">＋ 手动添加记忆</button>'
      + '<span id="addmemstat" class="mstat"></span></div>';
    html += '<div class="searchbar"><input id="qbox" type="search" inputmode="search" '
      + 'placeholder="搜索这个角色的记忆，回车确认" value="' + esc(q) + '"></div>';
    if (!(d.memories || []).length){
      html += '<div class="empty">暂无记忆</div>';
    } else {
      d.memories.forEach(function(m){ html += cardHtml(m); });
    }
    view.innerHTML = html;
    // [D-2 身份·性格] 异步拉档案填框（不阻塞主渲染）；保存走 memPost
    (function(){
      if (!document.getElementById('profbox')) { return; }
      get('/api/characters/' + encodeURIComponent(name) + '/profile').then(function(p){
        var sp = (p && p.static_profile) || {};
        var e1 = document.getElementById('profid');
        var e2 = document.getElementById('profpers');
        var e3 = document.getElementById('profappr');
        if (e1) { e1.value = sp['身份'] || ''; }
        if (e2) { e2.value = sp['性格'] || ''; }
        if (e3) { e3.value = sp['外貌'] || ''; }
      }).catch(function(){});
      // 别名独立端点
      get('/api/characters/' + encodeURIComponent(name) + '/aliases').then(function(a){
        var ea = document.getElementById('profalias');
        if (ea && a && a.aliases) { ea.value = a.aliases.join('、'); }
      }).catch(function(){});
      var sb = document.getElementById('saveprobtn');
      if (!sb) { return; }
      sb.addEventListener('click', function(){
        var e1 = document.getElementById('profid');
        var e2 = document.getElementById('profpers');
        var e3 = document.getElementById('profappr');
        var body = {
          '身份': e1 ? e1.value.trim() : '',
          '性格': e2 ? e2.value.trim() : '',
          '外貌': e3 ? e3.value.trim() : ''
        };
        var st = document.getElementById('prostat');
        sb.disabled = true;
        if (st) { st.textContent = '保存中…'; st.className = 'mstat'; }
        memPost('/api/characters/' + encodeURIComponent(name) + '/profile', body,
          function(j){
            sb.disabled = false;
            if (st) { st.textContent = '已保存'; st.className = 'mstat ok'; }
            uiToast('档案已保存', 'ok');
          },
          function(err){
            sb.disabled = false;
            if (st) { st.textContent = '保存失败'; st.className = 'mstat bad'; }
            uiAlert('保存失败：' + err.message, '保存失败', 'bad');
          });
        // 别名
        var ea = document.getElementById('profalias');
        var alist = [];
        if (ea && ea.value.trim()) {
          ea.value.split(/[,，、;；\s]+/).forEach(function(s){ s = s.trim(); if (s) alist.push(s); });
        }
        memPost('/api/characters/' + encodeURIComponent(name) + '/aliases',
                {aliases: alist}, function(){}, function(err){ uiAlert('别名保存失败：' + (err && err.message || err), '别名保存失败', 'bad'); });
      });
    })();
    // [手动记忆] 缓存当前角色的记忆 + 角色 id（供编辑弹窗预填 / 提交用）
    MEM_CACHE = {};
    (d.memories || []).forEach(function(m){ MEM_CACHE[String(m.memory_id)] = m; });
    MEM_CHAR = {id: (c.character_id === undefined ? null : c.character_id), name: c.name || ''};
    var addBtn = document.getElementById('addmembtn');
    if (addBtn){ addBtn.addEventListener('click', function(){ openMemEdit(null); }); }
    var box = document.getElementById('qbox');
    if (box){
      box.addEventListener('keydown', function(ev){
        if (ev.key === 'Enter'){ q = box.value.trim(); renderChar(name); }
      });
    }
  }).catch(function(e){
    view.innerHTML = '<a class="back" href="#/">← 返回卡片列表</a>'
      + '<div class="err">' + esc(e.message) + '</div>';
  });
}

// ===== V5.4：统计块弹层（底部滑出 / 半屏，点遮罩或关闭按钮收起）=====
var SHEETS = {
  messages: {
    url: '/api/messages?limit=100',
    ttl: '最近消息',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 按时间倒序（最多 100）'; },
    rows: function(d){
      return (d.items || []).map(function(m){
        return '<div class="srow"><div class="h">'
          + (m.is_user ? '🧑 用户' : '🎭 ' + esc(m.name || '?'))
          + (m.is_system ? ' · system' : '')
          + ' · ' + esc(String(m.send_date || '').slice(0,16))
          + '</div><p class="t">' + esc(m.mes || '') + '</p></div>';
      });
    }
  },
  events: {
    url: '/api/events?limit=100',
    ttl: '事件列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 按发生时间倒序'; },
    rows: function(d){
      return (d.items || []).map(function(e){
        return '<div class="srow"><div class="h">#' + esc(e.event_id)
          + ' · ' + esc(e.event_type || '') + ' · 重要 ' + f2(e.importance)
          + (e.location ? ' · ' + esc(e.location) : '')
          + ' · ' + esc(String(e.occurred_at || e.created_at || '').slice(0,16))
          + (e.is_factual ? '' : ' · 非事实')
          + '</div><p class="t">' + esc(e.summary || '') + '</p></div>';
      });
    }
  },
  memories: {
    url: '/api/memories?limit=100',
    ttl: '记忆列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 按创建时间倒序'; },
    rows: function(d){
      return (d.items || []).map(function(m){
        return '<div class="srow"><div class="h">👤 ' + esc(m.owner_name || '?')
          + ' · ' + esc(m.memory_type || '') + ' · 重要 ' + f2(m.importance)
          + ' · ' + esc(m.status || '')
          + (m.is_subjective ? ' · 主观' : '')
          + ' · ' + esc(String(m.created_at || '').slice(0,16))
          + '</div><p class="t">' + esc(m.content || '') + '</p></div>';
      });
    }
  },
  relationships: {
    url: '/api/relationships',
    ttl: '关系列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 组 · 角色两两之间'; },
    rows: function(d){
      return (d.relationships || []).map(function(r){
        return '<div class="srow"><div class="h">'
          + esc(r.from_name || '?') + ' → ' + esc(r.to_name || '?')
          + ' · ' + esc(String(r.updated_at || '').slice(0,16))
          + '</div><p class="t">信任 ' + f2(r.trust) + ' · 好感 ' + f2(r.affection)
          + ' · 怨恨 ' + f2(r.resentment) + ' · 熟悉 ' + f2(r.familiarity)
          + ' · 尊重 ' + f2(r.respect) + ' · 恐惧 ' + f2(r.fear)
          + ' · 依赖 ' + f2(r.dependency) + '</p>'
          + (r.state_summary
              ? '<div class="m">' + esc(r.state_summary) + '</div>' : '')
          + '</div>';
      });
    }
  },
  // ---- V5.5：另外 5 个块 ----
  visibility: {
    url: '/api/visibility?limit=100',
    ttl: '可见性列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 谁知道哪个事件'; },
    rows: function(d){
      return (d.items || []).map(function(v){
        return '<div class="srow"><div class="h">👤 ' + esc(v.character_name || '?')
          + ' · 事件 #' + esc(v.event_id) + ' · ' + esc(v.state || '')
          + (v.present ? ' · 在场' : ' · 不在场')
          + (v.role_in_event ? ' · ' + esc(v.role_in_event) : '')
          + ' · ' + esc(String(v.updated_at || '').slice(0,16))
          + '</div><p class="t">' + esc(v.event_summary || '（没有事件摘要）') + '</p>'
          + '<div class="m">来源 ' + esc(v.source || '?')
          + ' · 置信 ' + f2(v.confidence)
          + (v.partial_content ? ' · 只知道：' + esc(v.partial_content) : '')
          + '</div></div>';
      });
    }
  },
  beliefs: {
    url: '/api/beliefs?limit=100',
    ttl: '信念列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 按更新时间倒序'; },
    rows: function(d){
      return (d.items || []).map(function(b){
        return '<div class="srow"><div class="h">👤 ' + esc(b.owner_name || '?')
          + ' · ' + esc(b.kind || '') + '/' + esc(b.subject_kind || '')
          + ' · ' + esc(b.status || '') + ' · 置信 ' + f2(b.confidence)
          + ' · ' + esc(String(b.updated_at || '').slice(0,16))
          + '</div><p class="t">' + esc(b.statement || '') + '</p>'
          + (b.subject_ref ? '<div class="m">对象：' + esc(b.subject_ref) + '</div>' : '')
          + '</div>';
      });
    }
  },
  knowledge: {
    url: '/api/knowledge?limit=100',
    ttl: '知识列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 按更新时间倒序'; },
    rows: function(d){
      return (d.items || []).map(function(k){
        return '<div class="srow"><div class="h">👤 ' + esc(k.owner_name || '?')
          + ' · ' + esc(k.status || '') + ' · 置信 ' + f2(k.confidence)
          + ' · ' + esc(String(k.updated_at || k.created_at || '').slice(0,16))
          + '</div><p class="t">' + esc(k.subject || '') + '</p>'
          + (k.source ? '<div class="m">来源 ' + esc(k.source) + '</div>' : '')
          + '</div>';
      });
    }
  },
  commitments: {
    url: '/api/commitments?limit=100',
    ttl: '承诺列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 按创建时间倒序'; },
    rows: function(d){
      return (d.items || []).map(function(c){
        return '<div class="srow"><div class="h">'
          + esc(c.promiser_name || '?') + ' → '
          + esc(c.promisee_name || '（没指定对象）')
          + ' · ' + esc(c.status || '')
          + ' · ' + (c.deadline ? ('期限 ' + esc(c.deadline)) : '无期限')
          + ' · ' + esc(String(c.created_at || '').slice(0,16))
          + '</div><p class="t">' + esc(c.content || '') + '</p>'
          + (c.notes ? '<div class="m">' + esc(c.notes) + '</div>' : '')
          + '</div>';
      });
    }
  },
  secrets: {
    url: '/api/secrets?limit=100',
    ttl: '秘密列表',
    sub: function(d){ return '共 ' + esc(d.count) + ' 条 · 按创建时间倒序'; },
    rows: function(d){
      return (d.items || []).map(function(s){
        var known = (s.revealed_to || []);
        return '<div class="srow"><div class="h">👤 ' + esc(s.owner_name || '?')
          + ' · ' + esc(s.status || '')
          + (s.subject ? ' · 关于 ' + esc(s.subject) : '')
          + ' · ' + esc(String(s.created_at || '').slice(0,16))
          + '</div><p class="t">' + esc(s.content || '') + '</p>'
          + '<div class="m">已知晓：'
          + (known.length
              ? known.map(function(x){ return esc(x); }).join('、')
              : '（还没告诉任何人）')
          + '</div></div>';
      });
    }
  }
};
function sheetEsc(ev){ if (ev.key === 'Escape'){ closeSheet(); } }
function closeSheet(){
  var m = document.getElementById('sheetmask');
  if (m){ m.parentNode.removeChild(m); }
  document.removeEventListener('keydown', sheetEsc);
}
function openSheet(kind){
  var def = SHEETS[kind];
  if (!def){ return; }
  closeSheet();
  var mask = document.createElement('div');
  mask.className = 'sheetmask';
  mask.id = 'sheetmask';
  mask.innerHTML = '<div class="sheet" role="dialog" aria-modal="true">'
    + '<div class="sheethd"><div class="sheetttl">' + esc(def.ttl)
    + '<small id="sheetsub">载入中…</small></div>'
    + '<button class="sheetx" onclick="closeSheet()">关闭</button></div>'
    + '<div class="sheetbd" id="sheetbd"><div class="loading">载入中…</div></div>'
    + '</div>';
  mask.addEventListener('click', function(ev){
    if (ev.target === mask){ closeSheet(); }
  });
  document.body.appendChild(mask);
  document.addEventListener('keydown', sheetEsc);
  get(def.url).then(function(d){
    var sub = document.getElementById('sheetsub');
    var bd = document.getElementById('sheetbd');
    if (!bd){ return; }
    if (sub){ sub.innerHTML = def.sub(d); }
    var rows = def.rows(d);
    bd.innerHTML = rows.length ? rows.join('')
      : '<div class="empty">暂无数据</div>';
  }).catch(function(e){
    var bd = document.getElementById('sheetbd');
    if (bd){ bd.innerHTML = '<div class="err">' + esc(e.message) + '</div>'; }
  });
}

var sheetDeepDone = false;   // V5.4：?sheet=… 深链只认一次

// [V6 阶段D] 手动整理记忆：禁用 -> fetch -> 轮询 /api/merge_status
function mergeBoxHtml(){
  return '<div class="mergebar">'
    + '<button id="mergebtn" class="mbtn" type="button">手动整理当前卡记忆</button>'
    + '<span id="mergestat" class="mstat"></span></div>';
}
function setMergeStat(t, cls){
  var el = document.getElementById('mergestat');
  if (el){ el.textContent = t || ''; el.className = 'mstat' + (cls ? (' ' + cls) : ''); }
}
function mergeBtnIdle(label){
  var btn = document.getElementById('mergebtn');
  if (btn){ btn.disabled = false; btn.textContent = label || '手动整理当前卡记忆'; }
}
function pollMergeStatus(tries){
  tries = tries || 0;
  if (tries > 300){ setMergeStat('整理还在后台跑，稍后刷新看结果'); return; }
  get('/api/merge_status').then(function(d){
    if (d && d.running){
      setMergeStat('整理中…（已等 ' + (tries * 2) + ' 秒）');
      setTimeout(function(){ pollMergeStatus(tries + 1); }, 2000);
      return;
    }
    var r = (d && d.last_result) || {};
    setMergeStat('整理完成：扫描 ' + num(r.scanned) + ' 条 · 候选组 ' + num(r.groups)
      + ' · 合并 ' + num(r.merged) + ' 条（旧记忆只降级，不删除）', 'ok');
    mergeBtnIdle();
    setTimeout(function(){ route(); }, 1500);
  }).catch(function(e){
    setMergeStat('状态查询失败：' + e.message, 'bad');
    mergeBtnIdle();
  });
}
function startMerge(){
  var btn = document.getElementById('mergebtn');
  if (btn){ btn.disabled = true; btn.textContent = '整理中…'; }
  setMergeStat('已提交，等待后台整理…');
  fetch('/api/merge_memories', {method:'POST', cache:'no-store'}).then(function(r){
    return r.text().then(function(t){
      var j = null;
      try { j = JSON.parse(t); } catch (e) {}
      if (r.status === 409){
        setMergeStat('已有一轮整理在跑，稍后再试', 'bad');
        mergeBtnIdle();
        return;
      }
      if (r.status !== 202){
        throw new Error((j && j.error) || ('HTTP ' + r.status));
      }
      pollMergeStatus(0);
    });
  }).catch(function(e){
    setMergeStat('提交失败：' + e.message, 'bad');
    mergeBtnIdle();
  });
}
function wireMerge(){
  var btn = document.getElementById('mergebtn');
  if (!btn){ return; }
  btn.addEventListener('click', startMerge);
  // 刷新页面时如果后台还在跑，自动接上轮询
  get('/api/merge_status').then(function(d){
    if (d && d.running){
      btn.disabled = true; btn.textContent = '整理中…';
      pollMergeStatus(0);
    }
  }).catch(function(){});
}

// ===== [手动记忆] 手动新增 / 编辑 / 归档（纯原生 JS，无任何第三方库）=====
var MEM_CACHE = {};                       // memory_id -> 当前角色页的记忆对象
var MEM_CHAR = {id: null, name: ''};      // 当前角色
var MEM_SOURCES = [['USER','用户明确陈述'],['OBSERVATION','角色观察到'],['DIRECTIVE','既成事实元指令'],['INFERENCE','模型推断'],['HEARSAY','听他人转述'],['UNKNOWN','来源不明']];
var MEM_TYPES = [['episodic','经历'],['emotional','情绪'],['identity','身份'],
  ['relationship','关系'],['semantic','事实'],['preference','喜好'],
  ['procedural','习惯'],['commitment','承诺'],['secret','秘密'],
  ['conflict','冲突'],['world_event','世界事件']];
var MEM_TIERS = [[1,'1 核心（身份/不可逆）'],[2,'2 长期（重要）'],
  [3,'3 普通（默认）'],[4,'4 瞬时（此刻）']];

function memOpts(list, cur){
  return list.map(function(x){
    return '<option value="' + esc(x[0]) + '"'
      + (String(x[0]) === String(cur) ? ' selected' : '') + '>'
      + esc(x[1]) + '</option>';
  }).join('');
}
function setFMsg(t, cls){
  var el = document.getElementById('mfmsg');
  if (el){ el.textContent = t || ''; el.className = 'fmsg' + (cls ? (' ' + cls) : ''); }
}
// ===== [页面内弹窗] 替代 alert()/confirm()：纯原生 Modal + Toast，零第三方 =====
// 原生 alert/confirm 会阻塞渲染进程（CDP 自动化卡死、手机上也难看），本文件一律不用。
function uiEsc(ev){ if (ev.key === 'Escape'){ uiModalClose(); } }
function uiModalClose(){
  var m = document.getElementById('uimask');
  if (m && m.parentNode){ m.parentNode.removeChild(m); }
  document.removeEventListener('keydown', uiEsc);
}
function uiModal(o){
  o = o || {};
  uiModalClose();
  var lines = o.lines || (o.msg === undefined ? [] : [o.msg]);
  var body = '';
  for (var i = 0; i < lines.length; i++){
    var s = lines[i];
    if (s === null || s === undefined || s === ''){ body += '<div class="uigap"></div>'; continue; }
    body += '<div class="uiln">' + esc(String(s)) + '</div>';
  }
  if (o.kv){ body += '<div class="uikv">' + esc(String(o.kv)) + '</div>'; }
  if (o.html){ body += o.html; }
  var mask = document.createElement('div');
  mask.className = 'uimask';
  mask.id = 'uimask';
  mask.innerHTML = '<div class="uimod' + (o.danger ? ' danger' : '') + '" role="dialog" aria-modal="true">'
    + '<div class="uihd"><h3>' + esc(o.title || '提示') + '</h3></div>'
    + '<div class="uibd">' + body + '</div>'
    + '<div class="uift">'
    + (o.cancel ? '<button class="cancelbtn" type="button" id="uicancel">' + esc(o.cancelText || '取消') + '</button>' : '')
    + '<button class="savebtn' + (o.danger ? ' danger' : '') + '" type="button" id="uiok">' + esc(o.okText || '确定') + '</button>'
    + '</div></div>';
  mask.addEventListener('click', function(ev){ if (ev.target === mask){ uiModalClose(); } });
  document.body.appendChild(mask);
  document.addEventListener('keydown', uiEsc);
  var ok = document.getElementById('uiok');
  if (ok){
    ok.addEventListener('click', function(){
      // 先跑 onOk（此刻弹窗还在，能读到里面的输入框），之后再关闭
      if (o.onOk){ o.onOk(); }
      uiModalClose();
    });
    try { ok.focus(); } catch (e) {}
  }
  var cc = document.getElementById('uicancel');
  if (cc){ cc.addEventListener('click', uiModalClose); }
  return mask;
}
function uiAlert(msg, title, cls){
  return uiModal({title: title || '提示', lines: (msg instanceof Array ? msg : [msg]),
                  okText: '知道了', danger: (cls === 'bad')});
}
function uiConfirm(o){ return uiModal(o || {}); }
function uiToast(msg, cls){
  var old = document.getElementById('uitoast');
  if (old && old.parentNode){ old.parentNode.removeChild(old); }
  var t = document.createElement('div');
  t.className = 'uittoast' + (cls ? (' ' + cls) : '');
  t.id = 'uitoast';
  t.textContent = String(msg || '');
  document.body.appendChild(t);
  setTimeout(function(){ if (t && t.parentNode){ t.parentNode.removeChild(t); } }, 2400);
  return t;
}

function openMemEdit(mid){
  if (MEM_CHAR.id === null){
    uiAlert('请先从「卡片 → 角色」进入某个角色的记忆页，再加记忆。', '无法添加');
    return;
  }
  var m = (mid !== null && mid !== undefined) ? MEM_CACHE[String(mid)] : null;
  var isNew = !m;
  closeSheet();
  var mask = document.createElement('div');
  mask.className = 'sheetmask';
  mask.id = 'sheetmask';
  mask.innerHTML = '<div class="sheet" role="dialog" aria-modal="true">'
    + '<div class="sheethd"><div class="sheetttl">'
    + (isNew ? '手动添加记忆' : ('编辑记忆 #' + esc(m.memory_id)))
    + '<small>' + esc(MEM_CHAR.name) + (isNew ? ' · 手工写入，不调用 LLM' : ' · 保存后立即生效') + '</small>'
    + '</div><button class="sheetx" onclick="closeSheet()">关闭</button></div>'
    + '<div class="sheetbd"><div class="memform">'
    + '<label for="mfcontent">记忆正文</label>'
    + '<textarea id="mfcontent" placeholder="用这个角色的第一人称写，例如：那天晚上我怎么都睡不着…">'
    + esc(isNew ? '' : (m.content || '')) + '</textarea>'
    + '<div class="two">'
    + '<div><label for="mftype">类型</label><select id="mftype">'
    + memOpts(MEM_TYPES, isNew ? 'episodic' : m.memory_type) + '</select></div>'
    + '<div><label for="mftier">分层 tier</label><select id="mftier">'
    + memOpts(MEM_TIERS, isNew ? 3 : (m.tier || 3)) + '</select></div>'
    + '</div>'
    + '<label for="mfsource">来源 source_type</label><select id="mfsource">'
    + memOpts(MEM_SOURCES, isNew ? 'UNKNOWN' : (m.source_type || 'UNKNOWN'))
    + '</select>'
    + '<label for="mfimp">重要程度 <span id="mfimpv">'
    + (isNew ? '0.60' : f2(m.importance)) + '</span></label>'
    + '<input id="mfimp" type="range" min="0" max="1" step="0.05" value="'
    + (isNew ? '0.6' : num(m.importance, 0.6))
    + '" oninput="document.getElementById(\'mfimpv\').textContent=Number(this.value).toFixed(2)">'
    + '<div class="actions">'
    + '<button class="cancelbtn" type="button" onclick="closeSheet()">取消</button>'
    + '<button class="savebtn" id="mfsave" type="button">保存</button>'
    + '</div>'
    + '<div class="fmsg" id="mfmsg"></div>'
    + '</div></div></div>';
  mask.addEventListener('click', function(ev){ if (ev.target === mask){ closeSheet(); } });
  document.body.appendChild(mask);
  document.addEventListener('keydown', sheetEsc);
  var btn = document.getElementById('mfsave');
  if (btn){ btn.addEventListener('click', function(){ saveMem(mid); }); }
}
function memPost(url, body, onOk, onErr){
  fetch(url, {method:'POST', cache:'no-store',
              headers:{'Content-Type':'application/json'},
              body: JSON.stringify(body)})
    .then(function(r){
      return r.text().then(function(t){
        var j = null;
        try { j = JSON.parse(t); } catch (e) {}
        if (r.status >= 400 || !j || j.ok === false){
          throw new Error((j && j.error) || ('HTTP ' + r.status));
        }
        return j;
      });
    })
    .then(onOk)
    .catch(onErr);
}
function saveMem(mid){
  var ta = document.getElementById('mfcontent');
  var content = ta ? String(ta.value || '').trim() : '';
  if (!content){ setFMsg('正文不能为空', 'bad'); return; }
  var body = {
    memory_id: mid || null,
    owner_character_id: MEM_CHAR.id,
    content: content,
    memory_type: (document.getElementById('mftype') || {}).value,
    tier: parseInt((document.getElementById('mftier') || {}).value, 10),
    importance: parseFloat((document.getElementById('mfimp') || {}).value),
    source_type: (document.getElementById('mfsource') || {}).value
  };
  var btn = document.getElementById('mfsave');
  if (btn){ btn.disabled = true; btn.textContent = '保存中…'; }
  setFMsg('提交中…');
  memPost(mid ? '/api/memories/update' : '/api/memories/add', body, function(j){
    var tip = j.duplicated ? (j.message || '已存在同内容记忆') : (mid ? '已保存' : '已新增');
    setFMsg(tip, 'ok');
    uiToast(tip, j.duplicated ? '' : 'ok');
    setTimeout(function(){ closeSheet(); route(); }, 700);
  }, function(e){
    setFMsg('保存失败：' + e.message, 'bad');
    if (btn){ btn.disabled = false; btn.textContent = '保存'; }
  });
}
function memSetStatus(mid, status, okMsg){
  memPost('/api/memories/update', {memory_id: mid, status: status},
    function(){ if (okMsg){ uiToast(okMsg, 'ok'); } route(); },
    function(e){ uiAlert('操作失败：' + e.message, '操作失败', 'bad'); });
}
function archiveMem(mid){
  var m = MEM_CACHE[String(mid)] || {};
  var snip = String(m.content || '');
  if (snip.length > 80){ snip = snip.slice(0, 80) + '…'; }
  uiConfirm({
    title: '归档这条记忆？',
    lines: ['只改状态（active → archived），数据库里一行都不删。',
            '归档后不再注入上下文，随时可以恢复。'],
    kv: '内容：' + snip,
    cancel: true, okText: '归档', danger: true,
    onOk: function(){ memSetStatus(mid, 'archived', '已归档，可随时恢复'); }
  });
}
function unarchiveMem(mid){
  uiConfirm({
    title: '恢复这条记忆？',
    lines: ['状态改回 active，重新参与上下文注入。'],
    cancel: true, okText: '恢复',
    onOk: function(){ memSetStatus(mid, 'active', '已恢复为 active'); }
  });
}

// ===== [卡片逻辑删除] 删除 / 恢复一张卡（只改 is_active 标记，绝不 DELETE）=====
function setDelStat(t, cls){
  var el = document.getElementById('delcardstat');
  if (el){ el.textContent = t || ''; el.className = 'mstat' + (cls ? (' ' + cls) : ''); }
}
function deleteCard(name){
  if (!name){ return; }
  uiConfirm({
    title: '删除这张卡？',
    lines: ['只改状态（逻辑删除），数据库里一行都不删。',
            '卡下角色保持挂卡，随卡片一起从列表隐藏。',
            '反悔方式：卡片列表底部「已删除的卡片」里点恢复。'],
    kv: '卡名：' + name,
    cancel: true, okText: '删除', danger: true,
    onOk: function(){
      setDelStat('提交中…');
      memPost('/api/cards/delete', {name: name}, function(j){
        setDelStat('已删除（剩余可见卡 ' + num(j.cards_visible) + ' 张），返回列表…', 'ok');
        uiToast('已逻辑删除「' + name + '」', 'ok');
        setTimeout(function(){ location.hash = '#/'; route(); }, 700);
      }, function(e){
        setDelStat('删除失败：' + e.message, 'bad');
        uiAlert('删除失败：' + e.message, '删除失败', 'bad');
      });
    }
  });
}
function restoreCard(name){
  memPost('/api/cards/delete', {name: name, restore: true},
    function(){ uiToast('已恢复「' + name + '」', 'ok'); route(); },
    function(e){ uiAlert('恢复失败：' + e.message, '恢复失败', 'bad'); });
}

// ===== [V2.3 别名映射] 手动建卡 / 建角色（带别名），纯原生、零第三方 =====
function formField(id, label, ph, val){
  return '<label for="' + id + '">' + esc(label) + '</label>'
    + '<input id="' + id + '" type="text" autocomplete="off" placeholder="'
    + esc(ph || '') + '" value="' + esc(val || '') + '"'
    + ' style="width:100%;box-sizing:border-box;font:inherit;font-size:15px;'
    + 'padding:11px 12px;border-radius:12px;border:1px solid var(--line);'
    + 'margin:2px 0 12px">';
}
function openCardCreate(){
  uiModal({
    title: '新建卡片',
    html: formField('mcardname', '卡名（真名）', '例如：山田家')
        + formField('mcardalias', '卡片别名 / 关键词（可选，逗号分隔）', '例如：家庭, 日常'),
    lines: ['别名用于中继识别：Tavo 发来「家庭」也能命中这张卡。'],
    cancel: true, okText: '建立',
    onOk: saveCard
  });
}
function saveCard(){
  var nm = ((document.getElementById('mcardname') || {}).value || '').trim();
  var al = ((document.getElementById('mcardalias') || {}).value || '').trim();
  if (!nm){ uiAlert('卡名不能为空', '建卡失败', 'bad'); return; }
  memPost('/api/cards/create', {name: nm, aliases: al}, function(j){
    uiToast('已建立卡片「' + j.name + '」'
            + (j.aliases && j.aliases.length > 1
               ? '（别名 ' + j.aliases.slice(1).join('、') + '）' : ''), 'ok');
    route();
  }, function(e){ uiAlert('建卡失败：' + e.message, '建卡失败', 'bad'); });
}
function openCharCreate(cardName){
  uiModal({
    title: '添加角色到「' + cardName + '」',
    html: formField('mcharname', '角色名（真名）', '例如：山田一郎')
        + formField('mcharalias', '角色别名 / 称呼（可选，逗号分隔）', '例如：爸爸, 老爸'),
    lines: ['把「爸爸」这类称呼写进别名，Tavo 只写「爸爸」时也能挂到本角色名下。'],
    cancel: true, okText: '添加',
    onOk: function(){ saveChar(cardName); }
  });
}
function saveChar(cardName){
  var nm = ((document.getElementById('mcharname') || {}).value || '').trim();
  var al = ((document.getElementById('mcharalias') || {}).value || '').trim();
  if (!nm){ uiAlert('角色名不能为空', '建角色失败', 'bad'); return; }
  memPost('/api/characters/create', {name: nm, aliases: al, card: cardName},
    function(j){
      uiToast('已建立角色「' + j.name + '」并挂到「' + j.card_name + '」', 'ok');
      route();
    }, function(e){ uiAlert('建角色失败：' + e.message, '建角色失败', 'bad'); });
}

// ===== [角色隐藏] 逻辑隐藏 / 恢复一个角色（active 标记 + 记忆冻结，绝不 DELETE）=====
function hideChar(cid, name){
  uiConfirm({
    title: '隐藏这个角色？',
    lines: ['只改状态（characters.active = 0），数据库里一行都不删。',
            '它会从卡片的角色列表消失，不再出现在控制台（卡片归属保留）。',
            '它名下的记忆会暂时冻结（status 改 archived，随恢复一起解冻）。'],
    kv: '角色：' + name,
    cancel: true, okText: '隐藏', danger: true,
    onOk: function(){
      memPost('/api/characters/archive', {character_id: cid}, function(j){
        uiToast('已隐藏「' + name + '」（冻结记忆 '
                + num(j.memories_frozen) + ' 条）', 'ok');
        route();
      }, function(e){ uiAlert('隐藏失败：' + e.message, '隐藏失败', 'bad'); });
    }
  });
}
// [V2.7 彻底移除] 只打 purged_at 标记：从 UI 完全消失，行与记忆留档（绝不物理删除）
function purgeChar(cid, name){
  uiConfirm({
    title: '彻底移除这个角色？',
    lines: ['角色「' + name + '」将从 UI 完全消失。',
            '数据库中的行和它名下的记忆会保留，但不再显示。',
            '此项操作不可在 UI 里撤销。'],
    cancel: true, okText: '彻底移除', danger: true,
    onOk: function(){
      memPost('/api/characters/purge', {character_id: cid}, function(j){
        uiToast('已彻底移除「' + name + '」（行与记忆留档，一行没删）', 'ok');
        route();
      }, function(e){
        uiAlert('彻底移除失败：' + e.message, '彻底移除失败', 'bad');
      });
    }
  });
}
// [物理删除] 真删：角色 + 它名下全部数据（不可恢复）—— 全库唯一允许 DELETE 的入口
function deleteChar(cid, name){
  if (!confirm('确认永久删除角色【' + name + '】及其所有记忆？此操作不可恢复')){ return; }
  memPost('/api/characters/delete', {character_id: num(cid, 0)}, function(j){
    var d = j.deleted || {};
    uiToast('已永久删除「' + name + '」（记忆 ' + num(d.memories, 0) + ' 条）', 'ok');
    route();
  }, function(e){
    alert('删除失败：' + e.message);
  });
}

function unhideChar(cid, name){
  memPost('/api/characters/archive', {character_id: cid, restore: true},
    function(j){
      uiToast('已恢复「' + name + '」（解冻记忆 '
              + num(j.memories_restored) + ' 条）', 'ok');
      route();
    },
    function(e){ uiAlert('恢复失败：' + e.message, '恢复失败', 'bad'); });
}

// [整卡物理删除] 卡 + 全部角色 + 全部记忆/关系，一锅端（不可恢复，删前自动备份）
function purgeCardAll(name){
  memPost('/api/cards/purge', {name: name, dry_run: true},
    function(j){
      var c = j.counts || {};
      var labels = {
        cards: '卡片', characters: '角色', memories: '记忆', messages: '消息',
        beliefs: '信念', knowledge: '知识', secrets: '秘密',
        commitments: '承诺', relationships: '关系',
        relationship_history: '关系历史', character_states: '角色状态',
        state_history: '状态历史', event_visibility: '事件可见性',
        memory_conflicts: '记忆冲突', associations: '记忆关联',
        conversation_meta: '卡内设置', pending: '暂存回合',
        events_orphan: '孤儿事件'
      };
      var lines = [];
      Object.keys(c).forEach(function(k){
        if (c[k]) { lines.push((labels[k] || k) + '：' + c[k]); }
      });
      if (!lines.length) { lines.push('（这张卡几乎是空的）'); }
      lines.push('');
      lines.push('卡片、角色、记忆、关系全部删除，UI 里无法撤销。');
      lines.push('删除前会自动备份数据库（memory.db / -wal / -shm）。');
      uiConfirm({
        title: '彻底删除「' + name + '」？',
        lines: lines,
        kv: '将全部删除',
        cancel: true, okText: '确认全删', danger: true,
        onOk: function(){
          memPost('/api/cards/purge', {name: name, confirm: name},
            function(j2){
              var d = j2.deleted || {};
              uiToast('已删除「' + name + '」（角色 ' + num(d.characters, 0)
                      + ' 个 · 记忆 ' + num(d.memories, 0) + ' 条）', 'ok');
              location.hash = '#/';
              route();
            },
            function(e){ uiAlert('删除失败：' + e.message, '删除失败', 'bad'); });
        }
      });
    },
    function(e){ uiAlert('预检失败：' + e.message, '删除失败', 'bad'); });
}

function route(){
  var h = location.hash || '';
  if (h.indexOf('#/card/') === 0){
    q = '';
    renderCard(decodeURIComponent(h.slice(7)));
  } else if (h.indexOf('#/c/') === 0){
    q = '';
    renderChar(decodeURIComponent(h.slice(4)));
  } else {
    q = '';
    renderCards();
  }
  // V5.4：?sheet=messages|events|memories|relationships 直接开对应弹层
  var sm = /[?&]sheet=([a-z]+)/.exec(location.search || '');
  if (sm && !sheetDeepDone){ sheetDeepDone = true; openSheet(sm[1]); }
}

document.getElementById('refresh').addEventListener('click', route);
window.addEventListener('hashchange', route);
route();
</script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════
# 【18】Web 服务 + HTTP handler
# ══════════════════════════════════════════════════════════════════════

class WebServer:
    """记忆控制台 HTTP 后台（SPEC「Web 后台」段）。

    * 纯标准库 ``http.server``，HTML / CSS / JS 全部内嵌在 ``INDEX_HTML``
    * 默认 ``0.0.0.0:8081``，启动时打印本机 + 局域网（手机）访问地址
    * 所有 ``/api/*`` 都是**只读**接口，直接复用 ``MemoryEngine`` 的 manager
    * 任何异常都转成 JSON 错误响应，绝不把栈打到前端
    """

    def __init__(
        self,
        engine: MemoryEngine,
        host: Optional[str] = None,
        port: Optional[int] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.engine = engine
        self.host = str(host or engine.config.host or DEFAULT_HOST)
        self.port = int(port or engine.config.port or DEFAULT_PORT)
        self.logger = logger or _get_logger("web")
        self._httpd: Optional[Any] = None

    # ------------------------------------------------------------------
    # 地址
    # ------------------------------------------------------------------
    def urls(self) -> Dict[str, str]:
        """返回本机 / 局域网访问地址。"""
        lan = _local_ip()
        return {
            "local": "http://127.0.0.1:%d/" % self.port,
            "host": "http://%s:%d/" % (self.host, self.port),
            "lan": "http://%s:%d/" % (lan, self.port),
            "lan_ip": lan,
        }

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------
    def make_server(self) -> Any:
        """构造 ``ThreadingHTTPServer``（把 engine 挂在 server 上供 handler 取）。"""
        handler = _make_handler()
        httpd = _http_server.ThreadingHTTPServer(
            (self.host, self.port), handler)
        httpd.engine = self.engine  # type: ignore[attr-defined]
        httpd.weblog = self.logger  # type: ignore[attr-defined]
        httpd.daemon_threads = True
        self._httpd = httpd
        return httpd

    def banner(self) -> str:
        """启动横幅文本（打印到 stdout，手机照抄即可）。"""
        u = self.urls()
        return (
            "\n" + "=" * 62 + "\n"
            " %s %s  记忆控制台已启动\n" % (APP_NAME, APP_VERSION) + "=" * 62 + "\n"
            " 数据库   : %s\n" % self.engine.config.db_path +
            " 本机访问 : %s\n" % u["local"] +
            " 局域网   : %s\n" % u["lan"] +
            " 手机访问 : 连同一个 Wi-Fi，浏览器打开 %s\n" % u["lan"] +
            " 手机访问 : 连同一个 Wi-Fi，浏览器打开 %s\n" % u["lan"] +
            " 接口自检 : %shealth\n" % u["local"] +
            " 中继接口 : %s\n" % self.relay_url() +
            " 停止     : Ctrl + C\n" + "=" * 62 + "\n")

    def relay_url(self, character: Optional[str] = None) -> str:
        """中继接口的可粘贴地址（批 6 追加，给 Tavo / SillyTavern 用）。"""
        name = str(character
                   or getattr(self.engine.config.llm, "default_character", "")
                   or "").strip() or "角色名"
        url = "http://%s:%d%s?char=%s" % (self.urls()["lan_ip"], self.port,
                                          RELAY_PATH, name)
        if not bool(self.engine.config.llm.enabled):
            url += "   （llm.enabled=false，需先在 config.yaml 打开）"
        return url

    # ------------------------------------------------------------------
    # GET /v1/models（批 7 追加）
    # ------------------------------------------------------------------
    @staticmethod
    def models_payload(engine: MemoryEngine) -> Dict[str, Any]:
        """构造 ``GET /v1/models`` 的响应体（OpenAI 标准结构）。

        Tavo 连上本地中继后**先**拉模型列表，缺这个路由会一直卡在
        「正在加载模型列表」，最后 ``ConnectionResetError`` 断开。

        * 主条目 id 取自 ``config.llm.model``；为空、还是默认值
          （``LLM_DEFAULT_MODEL``）时退回 ``MODELS_FALLBACK_ID``
        * ``config.llm.default_character`` 非空时，额外追加一条
          ``<主 id>-<角色名>``，方便在客户端里选择特定角色
        """
        cfg = getattr(getattr(engine, "config", None), "llm", None)
        base = str(getattr(cfg, "model", "") or "").strip()
        if not base or base == LLM_DEFAULT_MODEL:
            base = MODELS_FALLBACK_ID

        def _entry(model_id: str) -> Dict[str, Any]:
            return {
                "id": model_id,
                "object": "model",
                "created": MODELS_CREATED_TS,
                "owned_by": MODELS_OWNED_BY,
            }

        data = [_entry(base)]
        character = str(getattr(cfg, "default_character", "") or "").strip()
        if character:
            data.append(_entry("%s-%s" % (base, character)))
        return {"object": "list", "data": data}

    def serve_forever(self, print_banner: bool = True) -> int:
        """启动服务并阻塞；``Ctrl+C`` 干净退出。"""
        try:
            httpd = self.make_server()
        except OSError as ex:
            self.logger.error("[Web] 端口 %s 无法绑定：%s", self.port, ex)
            print("启动失败：端口 %d 已被占用或被拒绝（%s）" % (self.port, ex))
            return 1
        if print_banner:
            print(self.banner(), flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n收到 Ctrl+C，正在停止…", flush=True)
        finally:
            self.stop()
        return 0

    def stop(self) -> None:
        """关闭服务。"""
        if self._httpd is None:
            return
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        try:
            self._httpd.server_close()
        except Exception:
            pass
        self._httpd = None
        self.logger.info("[Web] 已停止")


def _make_handler() -> Any:
    """构造绑定到 ``WebServer`` 的请求处理器类（延迟定义，避免污染全局）。"""

    class _Handler(_http_server.BaseHTTPRequestHandler):
        """只读 JSON API + 内嵌控制台页面。"""

        server_version = "%s/%s" % (APP_NAME, APP_VERSION)
        protocol_version = "HTTP/1.1"

        # ---- 基础工具 ----
        @property
        def engine(self) -> MemoryEngine:
            return getattr(self.server, "engine")  # type: ignore[no-any-return]

        @property
        def weblog(self) -> logging.Logger:
            return getattr(self.server, "weblog", None) or _get_logger("web")

        def log_message(self, fmt: str, *args: Any) -> None:
            self.weblog.debug("[Web] %s - %s", self.address_string(),
                              fmt % args)

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.weblog.debug("[Web] 客户端提前断开")
            except Exception as ex:
                self.weblog.warning("[Web] 响应写入失败：%s", ex)

        def _json(self, payload: Any, status: int = 200) -> None:
            try:
                text = json.dumps(payload, ensure_ascii=False, default=str)
            except Exception as ex:
                text = json.dumps({"error": "序列化失败：%s" % ex})
                status = 500
            self._send(status, text.encode(DEFAULT_ENCODING),
                       "application/json; charset=utf-8")

        def _err(self, message: str, status: int = 400) -> None:
            self._json({"error": message, "status": status}, status)

        def _html(self, text: str) -> None:
            self._send(200, text.encode(DEFAULT_ENCODING),
                       "text/html; charset=utf-8")

        # ---- 路由 ----
        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = _urlparse.urlsplit(self.path)
                path = _urlparse.unquote(parsed.path or "/")
                if len(path) > 1 and path.endswith("/"):
                    path = path.rstrip("/")
                qs = _urlparse.parse_qs(parsed.query or "")

                if path in ("", "/", "/index.html"):
                    return self._html(INDEX_HTML)
                if path == "/health":
                    return self._json({
                        "status": "ok", "app": APP_NAME,
                        "version": APP_VERSION,
                        "schema_version": SCHEMA_VERSION,
                        "db": str(self.engine.config.db_path),
                        "llm_enabled": bool(self.engine.llm.enabled),
                    })
                if path == "/api/characters":
                    return self._api_characters()
                # ---- V3 追加：三级 UI 的一级 / 二级数据源 ----
                if path == "/api/cards":
                    return self._api_cards()
                if path.startswith("/api/characters/") and path.endswith("/profile"):
                    raw_name = path[len("/api/characters/"):-len("/profile")]
                    return self._api_character_profile_get(raw_name)
                if path.startswith("/api/characters/") and path.endswith("/aliases"):
                    raw_name = path[len("/api/characters/"):-len("/aliases")]
                    return self._api_character_aliases_get(raw_name)

                if path.startswith("/api/cards/") and path.endswith(
                        "/characters"):
                    return self._api_card_characters(
                        path[len("/api/cards/"):-len("/characters")])
                if path.startswith("/api/cards/"):
                    return self._api_card(path[len("/api/cards/"):])
                if path == "/settings":
                    return self._html(SETTINGS_HTML)
                if path == "/api/settings":
                    return self._api_settings_get()
                if path == "/api/stats":
                    return self._json(self.engine.summary_stats())
                # ---- V5.4 追加：统计块弹层的只读列表（/api/relationships 已有）
                #      精确匹配必须写在下面 startswith 的**单角色**接口之前
                if path == "/api/messages":
                    return self._api_messages(qs)
                if path == "/api/events":
                    return self._api_events(qs)
                if path == "/api/memories":
                    return self._api_memories_all(qs)
                if path == "/api/visibility":
                    return self._api_visibility_all(qs)
                if path == "/api/beliefs":
                    return self._api_beliefs_all(qs)
                if path == "/api/knowledge":
                    return self._api_knowledge_all(qs)
                if path == "/api/commitments":
                    return self._api_commitments_all(qs)
                if path == "/api/secrets":
                    return self._api_secrets_all(qs)
                if path.startswith("/api/memories/"):
                    return self._api_memories(
                        path[len("/api/memories/"):], qs)
                if path.startswith("/api/context/"):
                    return self._api_context(
                        path[len("/api/context/"):], qs)
                if path == "/api/relationships":
                    return self._api_relationships()
                if path.startswith("/api/state/"):
                    return self._api_state(path[len("/api/state/"):])
                if path.startswith("/api/beliefs/"):
                    return self._api_beliefs(
                        path[len("/api/beliefs/"):], qs)
                if path.startswith("/api/visibility/"):
                    return self._api_visibility(
                        path[len("/api/visibility/"):], qs)
                if path == MODELS_PATH:
                    return self._api_models()
                # ---- [V6 阶段D] 合并状态（只读；前端轮询这个接口）----
                if path == MERGE_STATUS_PATH:
                    return self._api_merge_status()
                return self._err("未知路由：%s" % path, 404)
            except Exception as ex:
                self.weblog.exception("[Web] 请求处理异常：%s", ex)
                return self._err("%s: %s" % (type(ex).__name__, ex), 500)

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        # ---- 批 6 追加：本地 OpenAI 兼容中继（POST）----
        def do_OPTIONS(self) -> None:  # noqa: N802
            """CORS 预检（浏览器版 SillyTavern 跨域调用前会发过来）。"""
            try:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", RELAY_CORS_ORIGIN)
                self.send_header("Access-Control-Allow-Methods",
                                 "POST, GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers",
                                 "Content-Type, Authorization, %s"
                                 % RELAY_CHAR_HEADER)
                self.send_header("Access-Control-Max-Age", "86400")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                self.weblog.debug("[Web] 客户端提前断开（OPTIONS）")
            except Exception as ex:
                self.weblog.warning("[Web] OPTIONS 响应失败：%s", ex)

        def _read_body(self) -> Optional[bytes]:
            """读取 POST 请求体；长度非法/超限时已自行回包并返回 None。"""
            raw_len = self.headers.get("Content-Length")
            if raw_len is None:
                if str(self.headers.get("Transfer-Encoding") or "").lower().strip():
                    self._err("不支持 chunked 请求体，请带 Content-Length", 411)
                else:
                    self._err("缺少 Content-Length", 411)
                return None
            try:
                length = int(str(raw_len).strip())
            except Exception:
                self._err("Content-Length 非法：%r" % raw_len, 400)
                return None
            if length < 0:
                self._err("Content-Length 非法：%d" % length, 400)
                return None
            if length > RELAY_MAX_REQUEST_BYTES:
                self._err("请求体过大（%d 字节，上限 %d 字节）"
                          % (length, RELAY_MAX_REQUEST_BYTES), 413)
                return None
            if length == 0:
                return b""
            try:
                return self.rfile.read(length)
            except Exception as ex:
                self._err("读取请求体失败：%s" % ex, 400)
                return None

        def do_POST(self) -> None:  # noqa: N802
            """唯一的 POST 路由：``/v1/chat/completions``（OpenAI 兼容中继）。"""
            try:
                parsed = _urlparse.urlsplit(self.path)
                path = _urlparse.unquote(parsed.path or "/")
                if len(path) > 1 and path.endswith("/"):
                    path = path.rstrip("/")
                qs = _urlparse.parse_qs(parsed.query or "")

                # 批 7：模型列表只接受 GET，POST 过来明确回 405
                if path == MODELS_PATH:
                    return self._err(
                        "路由 %s 只接受 GET（405 Method Not Allowed）"
                        % MODELS_PATH, 405)

                # ---- [手动记忆] 控制台手动新增 / 编辑（都不是中继请求）----
                if path == MEM_ADD_PATH:
                    return self._api_memory_add()
                if path == MEM_UPDATE_PATH:
                    return self._api_memory_update()
                # ---- [卡片逻辑删除] 只改 is_active 标记，绝不 DELETE ----
                if path == CARD_DELETE_PATH:
                    return self._api_card_delete()
                # ---- [整卡物理删除] 卡 + 角色 + 全部记忆关系，真 DELETE ----
                if path == CARD_HARD_DELETE_PATH:
                    return self._api_card_hard_delete()
                # ---- [角色隐藏] 只改 characters.active（+ 记忆冻结），绝不 DELETE ----
                if path == CHAR_ARCHIVE_PATH:
                    return self._api_character_archive()
                if path == CHAR_PURGE_PATH:
                    return self._api_character_purge()
                # ---- [角色物理删除] 真删数据行 ----
                if path == CHAR_DELETE_PATH:
                    return self._api_character_delete()
                # ---- [V2.3 别名映射] 手动建卡 / 建角色（带别名）----
                if path == CARD_CREATE_PATH:
                    return self._api_card_create()
                if path.startswith("/api/characters/") and path.endswith("/profile"):
                    raw_name = path[len("/api/characters/"):-len("/profile")]
                    return self._api_character_profile_post(raw_name)
                if path.startswith("/api/characters/") and path.endswith("/aliases"):
                    raw_name = path[len("/api/characters/"):-len("/aliases")]
                    return self._api_character_aliases_post(raw_name)

                if path == CHAR_CREATE_PATH:
                    return self._api_character_create()

                if path == "/api/settings":
                    return self._api_settings_post()
                if path != RELAY_PATH and path != MERGE_PATH:
                    return self._err(
                        "未知路由（POST 只支持 %s、%s、%s、%s、%s、%s、%s、%s、%s）"
                        "：%s"
                        % (RELAY_PATH, MERGE_PATH, MEM_ADD_PATH, MEM_UPDATE_PATH,
                           CARD_DELETE_PATH, CHAR_ARCHIVE_PATH, CHAR_DELETE_PATH,
                           CARD_CREATE_PATH, CHAR_CREATE_PATH, path), 404)

                # ---- [V6 阶段D] 手动整理记忆：原子抢锁 -> 409 忙 / 202 已受理 ----
                if path == MERGE_PATH:
                    return self._api_merge_memories()

                raw = self._read_body()
                if raw is None:
                    return
                try:
                    payload = json.loads(
                        raw.decode(DEFAULT_ENCODING, errors="replace") or "{}")
                except Exception as ex:
                    return self._err("请求体不是合法 JSON：%s" % ex, 400)
                if not isinstance(payload, dict):
                    return self._err("请求体必须是 JSON 对象", 400)

                # 批 8：stream=true 走 SSE 流式转发；stream=false 走原逻辑
                if bool(payload.get("stream")):
                    return self._relay_stream(payload, qs)

                status, body, ctype = relay_chat_completions(
                    self.engine,
                    payload=payload,
                    query=qs,
                    char_header=self.headers.get(RELAY_CHAR_HEADER),
                    logger=self.weblog,
                    card_header=self.headers.get(RELAY_CARD_HEADER),
                )
                return self._send(status, body, ctype)
            except Exception as ex:
                self.weblog.exception("[Web] POST 请求处理异常：%s", ex)
                return self._err("%s: %s" % (type(ex).__name__, ex), 500)

        # ---- 批 8 追加：SSE 流式中继（stream=true）----
        def _sse_begin(self) -> bool:
            """发 SSE 响应头。

            流式响应**不能**带 ``Content-Length``，所以按 HTTP/1.1 用
            ``Transfer-Encoding: chunked`` 分块，由 ``_sse_write`` /
            ``_sse_end`` 负责分块编码（客户端照样看到裸的 ``data: ...``）。
            失败（客户端已断开）返回 False。
            """
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Access-Control-Allow-Origin",
                                 RELAY_CORS_ORIGIN)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                return True
            except (BrokenPipeError, ConnectionResetError):
                self.weblog.debug("[中继] 客户端提前断开（SSE 发头）")
                return False
            except Exception as ex:
                self.weblog.warning("[中继] SSE 响应头发送失败：%s", ex)
                return False

        def _sse_write(self, data: bytes) -> bool:
            """写一块 chunked 数据并**立即 flush**（每收到一块就推给客户端）。

            客户端已断开返回 False，调用方据此停止转发。
            """
            if not data:
                return True
            try:
                self.wfile.write(b"%x\r\n" % len(data))
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError):
                self.weblog.debug("[中继] 客户端提前断开（SSE 转发中）")
                return False
            except Exception as ex:
                self.weblog.warning("[中继] SSE 写入失败：%s", ex)
                return False

        def _sse_end(self) -> None:
            """写 chunked 结束块；失败静默（客户端可能已经走了）。"""
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                pass

        def _relay_stream(self, payload: Dict[str, Any],
                          qs: Dict[str, Any]) -> None:
            """处理 ``stream: true``：上游 SSE 原样转发给客户端。

            前置校验 / 角色识别 / 记忆注入 / 上游首块 peek 都在
            :func:`relay_chat_stream` 里完成 —— 失败时一个字节都还没发，
            所以这里能照常回普通 JSON 错误（400 / 404 / 502 / 503）。
            一旦开始转发，就只可能以「chunked 结束块」收尾。

            批 10 追加：转发时顺带累计 ``delta.content``，**流正常结束后**
            用后台线程调 ``ingest_turn`` 边聊边记（不阻塞、不拖慢响应）；
            上游报错或客户端提前取消都不回写。
            """
            error, chunks, meta = relay_chat_stream(
                self.engine,
                payload=payload,
                query=qs,
                char_header=self.headers.get(RELAY_CHAR_HEADER),
                logger=self.weblog,
                card_header=self.headers.get(RELAY_CARD_HEADER),
            )
            if error is not None:
                status, body, ctype = error
                return self._send(status, body, ctype)
            if chunks is None:
                return self._err("流式中继内部错误：没有拿到上游数据流", 500)
            if not self._sse_begin():
                try:
                    chunks.close()
                except Exception:
                    pass
                return

            sent = 0
            closed = False
            #: 累计这一轮 assistant 的正文（批 10：流结束后拿它去回写）
            delta_parts: List[str] = []
            try:
                for chunk in chunks:
                    if not self._sse_write(chunk):
                        closed = True   # 客户端走了，不再写（含结束块）
                        break
                    sent += 1
                    piece = _relay_stream_delta_text(chunk)
                    if piece:
                        delta_parts.append(piece)
            finally:
                try:
                    chunks.close()
                except Exception:
                    pass
                if not closed:
                    self._sse_end()
                self.weblog.info("[中继] 流式结束：转发 %d 段%s",
                                 sent, "（客户端提前断开）" if closed else "")
                # 批 10：只在「流正常结束」时回写（用户取消 / 上游报错都不写）
                # V3/V4：卡名要一起带下去（以前流式路径漏传了 card）；
                #        V4 起这一步只「暂存」，真正落库留到下一轮请求
                if not closed and meta:
                    _relay_ingest_turn(
                        self.engine, meta.get("character"),
                        meta.get("user_message"), "".join(delta_parts),
                        self.weblog, sync=False, card=meta.get("card"),
                        messages=meta.get("messages"))

        # ---- 各接口 ----
        def _api_settings_get(self) -> None:
            """返回当前配置（api_key 脱敏）。"""
            try:
                cfg = self.engine.config if hasattr(self, "engine") else None
                if cfg is None:
                    return self._json({"ok": False, "err": "no engine"})
                d = cfg.to_save_dict()
                # api_key 脱敏：只露前 4 + 后 4
                k = str((d.get("llm") or {}).get("api_key") or "")
                if len(k) > 12:
                    d["llm"]["api_key"] = k[:4] + "****" + k[-4:]
                elif k:
                    d["llm"]["api_key"] = "****"
                return self._json({"ok": True, "config": d,
                                   "source_path": cfg.source_path})
            except Exception as ex:
                return self._json({"ok": False, "err": str(ex)})

        def _api_settings_post(self) -> None:
            """接收 JSON，更新 config 对象，写盘，热加载。"""
            try:
                body = self._read_json_obj()
                if body is None:
                    return
                cfg = self.engine.config if hasattr(self, "engine") else None
                if cfg is None:
                    return self._json({"ok": False, "err": "no engine"})
                # 更新顶层
                for f in ("db_path", "debug", "host", "port"):
                    if f in body:
                        setattr(cfg, f, body[f])
                # 更新 llm / memory 子段
                for sec in ("llm", "memory"):
                    if isinstance(body.get(sec), dict):
                        tgt = getattr(cfg, sec)
                        for k, v in body[sec].items():
                            if k in tgt.__dataclass_fields__:
                                # api_key 里如果是脱敏字符串（含 ****）就跳过
                                if sec == "llm" and k == "api_key" and \
                                        (not str(v).strip() or "****" in str(v)):
                                    continue
                                setattr(tgt, k, v)
                cfg.validate()
                ok = cfg.save()
                # 热加载：把磁盘上的值再读回来（防止 save 写错）
                if ok:
                    hot_reload_config(cfg, cfg.source_path)
                return self._json({"ok": ok})
            except Exception as ex:
                return self._json({"ok": False, "err": str(ex)})

        def _api_models(self) -> None:
            """GET ``/v1/models``：OpenAI 格式模型列表（批 7 追加）。

            Tavo / SillyTavern 连上本地中继后先调这个接口；响应结构由
            :meth:`WebServer.models_payload` 生成，响应头由 ``_json``
            统一带上 ``Content-Type: application/json; charset=utf-8``
            与 ``Access-Control-Allow-Origin: *``。
            """
            payload = WebServer.models_payload(self.engine)
            self.weblog.debug("[中继] GET %s -> %d 个模型",
                              MODELS_PATH, len(payload["data"]))
            self._json(payload)

        # ---- [V6 阶段D] 追加：安全聚合合并的两个接口 ----
        def _api_merge_status(self) -> None:
            """GET ``/api/merge_status``：只读状态（前端轮询用）。

            * ``running=True``  -> 后台还有一轮在跑，继续轮询
            * ``last_result``   -> 最近一次的结果摘要（不落库，进程内）
            """
            payload = self.engine.merge_status()
            self.weblog.debug("[合并] GET %s -> running=%s",
                              MERGE_STATUS_PATH, payload["running"])
            self._json(payload)

        def _api_merge_memories(self) -> None:
            """POST ``/api/merge_memories``：手动触发一轮聚合合并。

            * **原子抢锁**：在 ``_merge_lock`` 里「读 ``_merge_running`` +
              置 True」，别人已经在跑就回 **409**；抢到回 **202** 并起后台线程。
            * 后台线程调
              ``merge_similar_memories(already_locked=True, manual_trigger=True)``，
              由它的 ``finally`` 负责 ``_merge_running = False``（防死锁）。
            * ``manual_trigger=True`` 的语义：**网页上点按钮 = 人为意志**，
              因此允许处理 tier1 核心记忆；只有自动轮（调度器）才无条件保护 tier1。
            * 请求体一律读完再丢弃：不读会让 keep-alive 连接上的下一个请求错位。
            """
            global _merge_running
            raw = self._read_body()
            if raw is None:
                return
            try:
                with _merge_lock:
                    if _merge_running:
                        self.weblog.info("[合并] POST %s -> 409 已有一轮在跑",
                                         MERGE_PATH)
                        return self._json({
                            "accepted": False, "busy": True, "running": True,
                            "message": "已有一轮整理正在进行（409）",
                            "last_at": _merge_last_at,
                            "last_result": _merge_last_result,
                        }, 409)
                    _merge_running = True
            except Exception as ex:
                return self._err("合并抢锁失败：%s" % ex, 500)

            def _run() -> None:
                try:
                    # 网页上点【手动整理当前卡记忆】= 明确的人为意志 ->
                    # manual_trigger=True，允许整理 tier1 核心记忆；
                    # 只有自动轮（调度器）才必须无条件保护 tier1。
                    self.engine.merge_similar_memories(already_locked=True,
                                                       manual_trigger=True)
                except Exception as ex:      # 兜底：绝不让标志位卡住
                    self.weblog.exception("[合并] 后台整理失败：%s", ex)
                    globals()["_merge_running"] = False

            try:
                th = threading.Thread(target=_run, name=MERGE_THREAD_NAME,
                                      daemon=True)
                th.start()
            except Exception as ex:
                _merge_running = False
                return self._err("合并后台线程启动失败：%s" % ex, 500)

            self.weblog.info("[合并] POST %s -> 202 已受理（后台整理中）",
                             MERGE_PATH)
            return self._json({
                "accepted": True, "busy": False, "running": True,
                "message": "已在后台开始整理记忆（202）",
                "status_url": MERGE_STATUS_PATH,
            }, 202)

        # ---- V3 追加：卡片层接口（三级 UI 的一级 / 二级）----
        def _user_char_names(self) -> List[str]:
            """V5.3：UI 认为「这是用户身份」的名字集合。

            = ``config.memory.user_names``（含 Tavo 认到的昵称、'User'、'明'）
              + 库里 ``is_user = 1`` 的角色名。
            这些名字**不是 AI 扮演的角色**，UI 不该当角色展示。
            """
            names: List[str] = []
            try:
                raw = getattr(self.engine.config.memory, "user_names", ()) or ()
                if isinstance(raw, str):
                    raw = [raw]
                for x in raw:
                    nm = str(x or "").strip()
                    if nm and nm not in names:
                        names.append(nm)
            except Exception:
                pass
            try:
                for r in self.engine.db.query(
                        "SELECT name FROM characters WHERE is_user = 1"):
                    nm = str(r.get("name") or "").strip()
                    if nm and nm not in names:
                        names.append(nm)
            except Exception:
                pass
            return names

        def _is_user_char(self, r: Dict[str, Any]) -> bool:
            """这一行是不是「用户身份」（is_user=1 或命中 user_names）。"""
            if bool(r.get("is_user")):
                return True
            nm = str(r.get("name") or "").strip()
            if not nm:
                return False
            if nm in self._user_char_names():
                return True
            try:
                return bool(self.engine._is_user_name(nm))
            except Exception:
                return False

        def _current_user_label(self) -> str:
            """UI 底部那行「当前用户：X」用谁：优先非 'User' 的那个名字。"""
            names = self._user_char_names()
            for nm in names:
                if nm.strip().lower() != "user":
                    return nm
            return names[0] if names else ""

        @staticmethod
        def _char_payload(r: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "character_id": r.get("character_id"),
                "name": r.get("name"),
                "role_type": r.get("role_type"),
                "is_user": bool(r.get("is_user")),
                "active": bool(r.get("active")),
                "card_id": r.get("card_id"),
                "message_count": int(r.get("message_count") or 0),
                "memory_count": int(r.get("memory_count") or 0),
                "belief_count": int(r.get("belief_count") or 0),
                "knowledge_count": int(r.get("knowledge_count") or 0),
                "aliases": [str(a) for a in _as_list(r.get("aliases"))],
            }

        def _api_cards(self) -> None:
            """GET ``/api/cards``：一级页面 —— 全部卡 + 散装 AI 角色 + 用户身份。

            老库里 ``characters.card_id`` 全为 NULL 时，本接口照样正常返回
            （``cards`` 为空数组，散装角色全部落在 ``loose`` 里）。

            **V5.3**：散装角色拆成两份 —— ``loose`` 只放 AI 扮演的角色，
            用户身份（``is_user=1`` 或命中 ``user_names``，如「明」「User」）
            单独放 ``users``，前端不把它们当角色显示（用户会以为"有三个我"）。
            """
            # [卡片逻辑删除] 可见卡 + 已删除卡（后者供一级页面「恢复」区用）
            cards_all = self.engine.card_mgr.list_all(include_inactive=True)
            cards = [c for c in cards_all if int(c.get("is_active", 1) or 0) == 1]
            inactive = [c for c in cards_all
                        if int(c.get("is_active", 1) or 0) == 0]
            loose_all = self.engine.card_mgr.loose_characters()
            loose = [r for r in loose_all if not self._is_user_char(r)]
            users = [r for r in loose_all if self._is_user_char(r)]
            # [角色隐藏] active=0 且非用户身份的角色 = 可恢复的「已隐藏」区
            hidden = [self._char_payload(c) for c in self.engine.char_mgr.all()
                      if not int(c.get("active") or 0)
                      and not self._is_user_char(c)]
            self._json({
                "count": len(cards),
                "cards": cards,
                "inactive_count": len(inactive),
                "inactive": inactive,
                "loose_count": len(loose),
                "loose": [self._char_payload(r) for r in loose],
                "users_count": len(users),
                "users": [self._char_payload(r) for r in users],
                "hidden_count": len(hidden),
                "hidden": hidden,
                "current_user": self._current_user_label(),
            })

        def _api_card(self, raw_name: str) -> None:
            """GET ``/api/cards/<card_name>``：单张卡的基本信息。"""
            name = _urlparse.unquote(raw_name or "").strip()
            card = self.engine.card_mgr.get(name) if name else None
            if card is None:
                return self._err("没找到卡：%s" % name, 404)
            chars = self.engine.card_mgr.list_characters(name)
            self._json({
                "card": {
                    "card_id": card.get("card_id"), "name": card.get("name"),
                    "source": card.get("source"),
                    "created_at": card.get("created_at"),
                    "last_seen": card.get("last_seen"),
                    "aliases": [str(a) for a in _as_list(card.get("aliases"))],
                },
                "count": len(chars),
            })

        def _api_character_profile_get(self, raw_name: str) -> None:
            """GET /api/characters/<name>/profile —— 读身份·性格。"""
            import urllib.parse as _up
            name = _up.unquote(raw_name) if "%" in raw_name else raw_name
            cid = self.engine.char_mgr.resolve_id(name)
            if cid is None:
                return self._err("角色不存在：%s" % name, 404)
            row = self.engine.db.query_one(
                "SELECT name, static_profile FROM characters WHERE character_id = ?", (cid,))
            if not row:
                return self._err("角色不存在：%s" % name, 404)
            prof = row.get("static_profile") or "{}"
            if isinstance(prof, str):
                try:
                    prof = json.loads(prof)
                except Exception:
                    prof = {}
            return self._json({
                "ok": True,
                "name": row.get("name") or name,
                "character_id": cid,
                "static_profile": prof,
            })

        def _api_character_profile_post(self, raw_name: str) -> None:
            """POST /api/characters/<name>/profile —— 写身份·性格·外貌（手填，合并语义）。"""
            import urllib.parse as _up
            name = _up.unquote(raw_name) if "%" in raw_name else raw_name
            body = self._read_json_obj()
            if body is None:
                return
            if not isinstance(body, dict):
                return self._err("请求体必须是 JSON 对象", 400)
            cid = self.engine.char_mgr.resolve_id(name)
            if cid is None:
                return self._err("角色不存在：%s" % name, 404)
            # [合并语义] 读旧档案 → 未知 key 原样保留，三个已知 key 用新值覆盖
            # （新值为空 = 删掉该 key；其余键一概不动）
            row = self.engine.db.query_one(
                "SELECT static_profile FROM characters WHERE character_id = ?", (cid,))
            old = (row or {}).get("static_profile") or "{}"
            if isinstance(old, str):
                try:
                    old = json.loads(old)
                except Exception:
                    old = {}
            if not isinstance(old, dict):
                old = {}
            merged = dict(old)
            for k in ("身份", "性格", "外貌"):
                if k not in body:
                    continue          # 键缺席 → 不动
                v = str(body.get(k) or "").strip()
                if v:
                    merged[k] = v
                elif k in merged:
                    del merged[k]     # 显式空串 → 删
            if not self.engine.char_mgr.set_static_profile(name, merged):
                return self._err("写入失败", 500)
            return self._json({"ok": True})

        def _api_character_aliases_get(self, raw_name: str) -> None:
            """GET /api/characters/<name>/aliases —— 读别名列表。"""
            import urllib.parse as _up
            name = _up.unquote(raw_name) if "%" in raw_name else raw_name
            cid = self.engine.char_mgr.resolve_id(name)
            if cid is None:
                return self._err("角色不存在：%s" % name, 404)
            row = self.engine.db.query_one(
                "SELECT name, aliases FROM characters WHERE character_id = ?", (cid,))
            if not row:
                return self._err("角色不存在：%s" % name, 404)
            al = row.get("aliases") or "[]"
            if isinstance(al, str):
                try:
                    al = json.loads(al)
                except Exception:
                    al = []
            if not isinstance(al, list):
                al = []
            al = [str(x) for x in al if isinstance(x, str) and str(x).strip()]
            return self._json({
                "ok": True,
                "name": row.get("name") or name,
                "character_id": cid,
                "aliases": al,
            })

        def _api_character_aliases_post(self, raw_name: str) -> None:
            """POST /api/characters/<name>/aliases —— 整体替换别名列表。"""
            import urllib.parse as _up
            name = _up.unquote(raw_name) if "%" in raw_name else raw_name
            body = self._read_json_obj()
            if body is None:
                return
            if not isinstance(body, dict):
                return self._err("请求体必须是 JSON 对象", 400)
            al_in = body.get("aliases")
            if not isinstance(al_in, list):
                return self._err("aliases 必须是数组", 400)
            al = []
            seen = set()
            for x in al_in:
                s = str(x).strip()
                if s and s not in seen:
                    seen.add(s)
                    al.append(s)
            cid = self.engine.char_mgr.resolve_id(name)
            if cid is None:
                return self._err("角色不存在：%s" % name, 404)
            try:
                self.engine.db.execute(
                    "UPDATE characters SET aliases = ? WHERE character_id = ?",
                    (json.dumps(al, ensure_ascii=False), cid))
            except Exception as ex:
                return self._err("写入失败：%s" % ex, 500)
            return self._json({"ok": True, "aliases": al})

        def _api_card_characters(self, raw_name: str) -> None:
            """GET ``/api/cards/<card_name>/characters``：二级页面数据源。"""
            name = _urlparse.unquote(raw_name or "").strip()
            card = self.engine.card_mgr.get(name) if name else None
            if card is None:
                return self._err("没找到卡：%s" % name, 404)
            # [角色隐藏修复] 必须带 include_inactive —— 否则 chars_all 里
            # 已经滤掉了 active=0 的角色，下面的 hidden_chars 恒为空，
            # 二级页的「已隐藏」区永远渲染不出来（恢复按钮也就无从点击）。
            chars_all = [r for r in self.engine.card_mgr.list_characters(
                name, include_inactive=True) if not self._is_user_char(r)]
            # [角色隐藏] active=0 的角色不在二级页展示（一级页有「已隐藏」区可恢复）
            chars = [r for r in chars_all if int(r.get("active") or 0)]
            hidden_chars = [r for r in chars_all if not int(r.get("active") or 0)]
            self._json({
                "card": {
                    "card_id": card.get("card_id"), "name": card.get("name"),
                    "source": card.get("source"),
                    "created_at": card.get("created_at"),
                    "last_seen": card.get("last_seen"),
                    "aliases": [str(a) for a in _as_list(card.get("aliases"))],
                    "character_count": len(chars),
                    "memory_count": sum(
                        int(c.get("memory_count") or 0) for c in chars),
                },
                "count": len(chars),
                "hidden_count": len(hidden_chars),
                "characters": [self._char_payload(r) for r in chars],
                "hidden_characters": [self._char_payload(r)
                                     for r in hidden_chars],
            })

        def _api_characters(self) -> None:
            """GET ``/api/characters``：全库角色列表（含记忆/信念/知识计数）。

            **V5.3**：``characters`` 只给 AI 扮演的角色；用户身份
            （``is_user=1`` / 命中 ``user_names``）单独放 ``users``。
            """
            rows = self.engine.list_characters(with_counts=True)
            out: List[Dict[str, Any]] = []
            users: List[Dict[str, Any]] = []
            for r in rows:
                item = {
                    "character_id": r.get("character_id"),
                    "name": r.get("name"),
                    "role_type": r.get("role_type"),
                    "is_user": bool(r.get("is_user")),
                    "active": bool(r.get("active")),
                    "message_count": int(r.get("message_count") or 0),
                    "memory_count": int(r.get("memory_count") or 0),
                    "belief_count": int(r.get("belief_count") or 0),
                    "knowledge_count": int(r.get("knowledge_count") or 0),
                    "card_id": r.get("card_id"),
                    "aliases": [str(a) for a in _as_list(r.get("aliases"))],
                }
                (users if self._is_user_char(r) else out).append(item)
            self._json({"count": len(out), "characters": out,
                        "users_count": len(users), "users": users,
                        "current_user": self._current_user_label()})

        def _character_or_404(self, raw_name: str) -> Optional[Dict[str, Any]]:
            name = raw_name.strip()
            row = self.engine.char_mgr.get(name) if name else None
            if row is None:
                self._err("没找到角色：%s" % name, 404)
                return None
            return row

        @staticmethod
        def _mem_payload(mem: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(mem)
            out.pop("_debug", None)
            if out.get("_score") is not None:
                out["_score"] = float(out["_score"])
            out["tags"] = [str(t) for t in _as_list(mem.get("tags"))]
            for key, dv in (("importance", DEFAULT_IMPORTANCE),
                            ("confidence", DEFAULT_CONFIDENCE),
                            ("emotional_intensity", DEFAULT_EMOTIONAL_INTENSITY)):
                out[key] = _clamp(mem.get(key), 0.0, 1.0, dv)
            try:
                out["recall_strength"] = float(
                    mem.get("recall_strength") or DEFAULT_RECALL_STRENGTH)
            except Exception:
                out["recall_strength"] = DEFAULT_RECALL_STRENGTH
            return out

        # ==============================================================
        # [手动记忆] 控制台手动新增 / 编辑 / 归档（局部新增，纯标准库）
        #   * 新增 -> 走 MemoryManager.add_memory()，dedup_hash 由引擎内部算
        #   * 编辑 -> 参数化 UPDATE；正文/类型变了就**重算 dedup_hash**
        #   * 归档 -> 逻辑删除：只把 status 改成 archived，**绝不 DELETE**
        # ==============================================================
        def _read_json_obj(self) -> Optional[Dict[str, Any]]:
            """读 POST body 并解析成 dict；失败时已回错误响应，返回 None。"""
            raw = self._read_body()
            if raw is None:
                return None
            try:
                payload = json.loads(
                    raw.decode(DEFAULT_ENCODING, errors="replace") or "{}")
            except Exception as ex:
                self._err("请求体不是合法 JSON：%s" % ex, 400)
                return None
            if not isinstance(payload, dict):
                self._err("请求体必须是 JSON 对象", 400)
                return None
            return payload

        def _payload_owner_id(self, payload: Dict[str, Any]) -> Optional[int]:
            """解析 owner（character_id 或名字）-> character_id；失败时已回错误。"""
            cid = _to_int(payload.get("owner_character_id"))
            if cid is None:
                cid = self.engine.char_mgr.resolve_id(payload.get("owner"))
            row = self.engine.char_mgr.get(cid) if cid is not None else None
            if row is None:
                self._err("没找到角色：%s"
                          % (payload.get("owner_character_id")
                             or payload.get("owner") or "?"), 404)
                return None
            if self._is_user_char(row):
                self._err("「%s」是用户角色，按引擎规则不建记忆"
                          % row.get("name"), 400)
                return None
            return int(row["character_id"])

        @staticmethod
        def _clean_aliases(raw: Any) -> List[str]:
            """别名入参归一化：支持 list，也支持「家庭, 日常」这种中英文逗号串。"""
            if raw is None:
                return []
            if isinstance(raw, str):
                parts = re.split(r"[,，、;；\s]+", raw)
            elif isinstance(raw, (list, tuple, set)):
                parts = []
                for x in raw:
                    parts.extend(re.split(r"[,，、;；\s]+", str(x)))
            else:
                parts = [str(raw)]
            out: List[str] = []
            for x in parts:
                sx = str(x).strip()
                if sx and sx not in out and len(out) < ALIAS_MAX_COUNT:
                    out.append(sx)
            return out

        def _api_card_create(self) -> None:
            """POST ``/api/cards/create`` —— 手动建卡（可带别名/关键词）。

            JSON 参数：``name``（必填）、``aliases``（可选，数组或「家庭,日常」字符串）

            * 卡名已存在（或命中某张卡的**别名**）→ 不重复建卡，只补记别名；
            * 别名写进 ``cards.aliases``（JSON 数组），中继识别时按
              **真名 → 别名** 的顺序匹配（见 SPEC 1.4 / 识别段 3f）。
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            name = _relay_fix_text(payload.get("name")).strip()
            if not name:
                self._err("卡名（name）不能为空", 400)
                return
            aliases = self._clean_aliases(payload.get("aliases"))
            existed = self.engine.card_mgr.resolve_by_alias(name)
            cid = self.engine.card_mgr.get_or_create(name, aliases=aliases)
            if cid is None:
                self._err("建卡失败（详见日志）", 500)
                return
            card = self.engine.card_mgr.get(cid) or {}
            self.weblog.info(
                "[卡片] 手动%s卡 id=%s name=%s 别名=%s",
                "复用" if existed else "建", cid, card.get("name"),
                "、".join(self.engine.card_mgr.aliases_of(cid)) or "无")
            self._json({"ok": True, "card_id": cid,
                        "name": card.get("name"),
                        "aliases": self.engine.card_mgr.aliases_of(cid),
                        "reused": bool(existed)}, 200)

        def _api_character_create(self) -> None:
            """POST ``/api/characters/create`` —— 手动建角色（可带别名/称呼）。

            JSON 参数：``name``（必填）、``aliases``（可选）、``card``（可选卡名）、
            ``role_type``（可选）

            * 角色名/别名已存在 → 复用（不重复建号），只补记别名；
            * ``card`` 省略时按 **SPEC 1.4 铁律** 挂到兜底卡「默认卡」；
            * 别名写进 ``characters.aliases``，中继识别时「爸爸」会自动映射到它。
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            name = _relay_fix_text(payload.get("name")).strip()
            if not name:
                self._err("角色名（name）不能为空", 400)
                return
            aliases = self._clean_aliases(payload.get("aliases"))
            card_name = _relay_fix_text(payload.get("card")).strip()
            role_type = str(payload.get("role_type") or "").strip() or None
            existed = self.engine.char_mgr.resolve_name(name)
            row = self.engine.char_mgr.get_or_create(name, role_type=role_type,
                                                     aliases=aliases)
            if row is None:
                self._err("建角色失败（详见日志）", 500)
                return
            cid = int(row["character_id"])
            target = card_name or DEFAULT_CARD_NAME
            card_id = self.engine.card_mgr.get_or_create(target)
            if card_id is not None:
                self.engine.card_mgr.attach_character(card_id, cid)
            real = self.engine.char_mgr.get(cid) or row
            self.weblog.info(
                "[角色] 手动%s角色 id=%s name=%s 别名=%s 卡=%s",
                "复用" if existed else "建", cid, real.get("name"),
                "、".join(str(a) for a in _as_list(real.get("aliases"))) or "无",
                target)
            self._json({"ok": True, "character_id": cid, "name": real.get("name"),
                        "aliases": [str(a) for a in _as_list(real.get("aliases"))],
                        "card_id": card_id, "card_name": target,
                        "reused": bool(existed)}, 200)

        def _frozen_ids(self, key: str) -> List[int]:
            """读 ``char_freeze:<cid>`` 里登记的被冻结 memory_id 列表。"""
            raw = self.engine.db.get_meta(key)
            if not raw:
                return []
            try:
                data = json.loads(raw)
            except Exception:
                return []
            out: List[int] = []
            for x in (data.get("memory_ids") or []):
                try:
                    out.append(int(x))
                except Exception:
                    continue
            return out

        def _api_character_archive(self) -> None:
            """POST ``/api/characters/archive`` —— 逻辑隐藏 / 恢复一个角色。

            JSON 参数：``character_id``（或 ``name``）、``restore``（可选，true=恢复）

            **绝不 DELETE，只改状态**：

            * 隐藏 = ``characters.active = 0`` + 该角色**当前 active 的记忆**一并
              逻辑归档（``status='archived'`` = 暂时冻结），受影响的 ``memory_id``
              登记进 ``conversation_meta`` 的 ``char_freeze:<id>`` 键；
            * 恢复 = ``active = 1`` + **只把登记过的那批**记忆改回 ``active``
              （不碰其它历史归档）；
            * 用户身份（``is_user=1`` / 命中 ``user_names``）**禁止隐藏** → 400。
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            ref = payload.get("character_id")
            if ref in (None, ""):
                ref = payload.get("name")
            if ref in (None, ""):
                self._err("需要 character_id 或 name", 404)
                return
            ch = self.engine.char_mgr.get(ref)
            if ch is None:
                self._err("没找到角色：%s" % ref, 404)
                return
            cid = int(ch["character_id"])
            name = str(ch.get("name") or "")
            if self._is_user_char(ch):
                self._err("「%s」是用户身份（不参与记忆），不允许隐藏" % name, 400)
                return
            key = CHAR_FREEZE_META_PREFIX + str(cid)
            logger = getattr(self.engine, "logger", None)

            if payload.get("restore"):
                frozen = self._frozen_ids(key)
                back = 0
                self.engine.char_mgr.set_active(cid, True)
                # [V2.7] 恢复 = 连「彻底移除」标记一起撤掉
                # （UI 上不可达：已移除的角色不显示；仅直接调 API 时用得上）
                if str(ch.get("purged_at") or "").strip():
                    self.engine.db.execute(
                        "UPDATE characters SET purged_at = NULL "
                        "WHERE character_id = ?", (cid,))
                    if logger:
                        logger.info("[角色移除] 恢复角色「%s」id=%s：purged_at 已清空",
                                    name, cid)
                for mid in frozen:
                    cur = self.engine.db.execute(
                        "UPDATE memories SET status = ? "
                        "WHERE memory_id = ? AND status = ?",
                        (MEM_STATUS_ACTIVE, int(mid), MEM_STATUS_ARCHIVED))
                    if cur is not None:
                        back += 1
                self.engine.db.set_meta(
                    key, json.dumps({"memory_ids": [],
                                     "restored_at": now_iso()},
                                    ensure_ascii=False))
                if logger:
                    logger.info("[角色隐藏] 恢复角色「%s」id=%s：active=1，"
                                "解冻记忆 %d 条（只改状态，一行没删）",
                                name, cid, back)
                self._json({"ok": True, "action": "restore", "character_id": cid,
                            "name": name, "active": True,
                            "memories_restored": back,
                            "loose_count": self.engine.card_mgr.loose_count()})
                return

            rows = self.engine.db.query(
                "SELECT memory_id FROM memories "
                "WHERE owner_character_id = ? AND status = ?",
                (cid, MEM_STATUS_ACTIVE))
            ids = [int(r["memory_id"]) for r in rows
                   if r.get("memory_id") is not None]
            self.engine.char_mgr.set_active(cid, False)
            for mid in ids:
                self.engine.db.execute(
                    "UPDATE memories SET status = ? WHERE memory_id = ?",
                    (MEM_STATUS_ARCHIVED, mid))
            self.engine.db.set_meta(
                key, json.dumps({"memory_ids": ids, "hidden_at": now_iso()},
                                ensure_ascii=False))
            if logger:
                logger.info("[角色隐藏] 隐藏角色「%s」id=%s：active=0，"
                            "冻结记忆 %d 条（只改状态，一行没删；"
                            "恢复用 restore=true）", name, cid, len(ids))
            self._json({"ok": True, "action": "hide", "character_id": cid,
                        "name": name, "active": False,
                        "memories_frozen": len(ids), "memory_ids": ids,
                        "loose_count": self.engine.card_mgr.loose_count()})

        def _api_character_purge(self) -> None:
            """POST ``/api/characters/purge`` —— 「彻底移除」一个角色（**只打标记**）。

            JSON 参数：``character_id``（或 ``name``）

            **铁律：绝不 DELETE 行。** 语义 = 给 ``characters.purged_at`` 打时间戳
            → 该角色从所有 UI 列表消失；它名下的记忆**原样留档**（不转移 / 不删除 /
            不改归属）。反悔途径：``/api/characters/archive`` 带 ``restore=true``。

            校验（防手滑）：
            * 角色必须存在 → 404
            * ``is_user = 1`` 用户身份禁止 → 400
            * 必须**先隐藏**（``active = 0``）→ 否则 400
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            logger = getattr(self.engine, "logger", None)
            ref = payload.get("character_id")
            if ref in (None, ""):
                ref = payload.get("name")
            if ref in (None, ""):
                self._err("需要 character_id 或 name", 404)
                return
            ch = self.engine.char_mgr.get(ref)
            if ch is None:
                self._err("没找到角色：%s" % ref, 404)
                return
            cid = int(ch["character_id"])
            name = str(ch.get("name") or "")
            if self._is_user_char(ch):
                self._err("「%s」是用户身份，不允许彻底移除" % name, 400)
                return
            if int(ch.get("active") or 0) != 0:
                self._err("「%s」仍是活跃角色（active=1），请先【归档/隐藏】再彻底移除"
                          "（防止手滑删掉活跃角色）" % name, 400)
                return
            if str(ch.get("purged_at") or "").strip():
                self._json({"ok": True, "purged": True, "already": True,
                            "character_id": cid, "name": name,
                            "purged_at": ch.get("purged_at")})
                return
            stamp = now_iso()
            cur = self.engine.db.execute(
                "UPDATE characters SET purged_at = ? WHERE character_id = ?",
                (stamp, cid))
            if cur is None:
                self._err("彻底移除失败：purged_at 写入未生效", 500)
                return
            try:
                hidden_left = [c for c in self.engine.char_mgr.all()
                               if not int(c.get("active") or 0)
                               and not self._is_user_char(c)]
            except Exception:
                hidden_left = []
            if logger:
                logger.info(
                    "[角色移除] 角色「%s」id=%s 已标记 purged_at=%s，行未删除，记忆留档",
                    name, cid, stamp)
            self._json({"ok": True, "purged": True, "character_id": cid,
                        "name": name, "purged_at": stamp,
                        "hidden_count": len(hidden_left)})

        def _api_character_delete(self) -> None:
            """POST ``/api/characters/delete`` —— **物理删除**角色及其全部数据。

            JSON 参数：``character_id``（或 ``name``）

            [用户明确要求] 全库**唯一**允许真删数据行的入口，**不可恢复**。
            与 ``/archive``（只改 active）、``/purge``（只打 purged_at）不同，
            这里真的 ``DELETE FROM``。

            表清单**动态枚举、不硬编码**：扫 ``sqlite_master`` 全部表，用
            ``PRAGMA table_info`` 找
            列名 == ``character_id`` / 以 ``_character_id`` 结尾，
            以及列名 == ``memory_id`` / 以 ``_memory_id`` 结尾 / ``memory_a`` /
            ``memory_b``（associations 的列名不叫 *_memory_id，必须点名，
            否则会漏），逐列生成 DELETE。

            顺序：先删引用表（按 id 命中）→ 再删 memories（按 owner）→
            最后删 characters。全程单事务，任一步失败整批回滚。
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            logger = getattr(self.engine, "logger", None)
            ref = payload.get("character_id")
            if ref in (None, ""):
                ref = payload.get("name")
            if ref in (None, ""):
                self._err("需要 character_id", 404)
                return
            ch = self.engine.char_mgr.get(ref)
            if ch is None:
                self._err("没找到角色：%s" % (ref,), 404)
                return
            cid = int(ch["character_id"])
            name = str(ch.get("name") or "")
            if self._is_user_char(ch):
                self._err("「%s」是用户身份，不允许物理删除" % name, 400)
                return

            db = self.engine.db
            deleted: Dict[str, int] = {}
            try:
                with db.transaction():
                    mids = [int(r["memory_id"]) for r in db.query(
                        "SELECT memory_id FROM memories "
                        "WHERE owner_character_id = ?", (cid,))]

                    # ---- 引用扫描（按「值命中」删，不靠列名模式）----
                    # 候选列判定（两种，白名单外一律不碰，防止误删）：
                    #   A) 声明了外键且指向 characters / memories 的列 —— 权威来源，
                    #      能覆盖 promiser_id / promisee_id / memory_a / memory_b
                    #      这类名字不规则的列。
                    #   B) 没有任何外键声明、但列名以 "_id" 结尾的列 —— 覆盖
                    #      messages.character_id / state_history.character_id /
                    #      relationship_history.from_character_id 这些裸列。
                    # 排除本表主键：否则 character_id 与 memory_id 数值撞车时
                    # （cid=9 恰好等于某条 memory_id=9）会把别人的行误删。
                    tables = []
                    for r in db.query("SELECT name FROM sqlite_master "
                                      "WHERE type = 'table'"):
                        t = str(r.get("name") or "")
                        if t and not t.startswith("sqlite_"):
                            tables.append(t)

                    plan = []          # [(表名, [(列名, [命中值, ...]), ...])]
                    for t in tables:
                        if t == "characters":
                            continue
                        try:
                            info = list(db.query("PRAGMA table_info(%s)" % t))
                        except Exception:
                            continue
                        cols = [str(c.get("name") or "") for c in info]
                        pk = set(str(c.get("name") or "") for c in info
                                 if _to_int(c.get("pk")))
                        # ---- 列归属分派 [修复 2026-10-03] --------------------------------
                        # 旧实现把「所有以 _id 结尾的列」收进同一个候选集，然后对**每一列**
                        # 同时拿 cid 和 mids 去比。于是 messages.character_id 会拿 memory_id
                        # 列表去查 —— 两个 id 空间撞车时（memory_id=26 恰好等于某个角色的的
                        # character_id=26）就把别人的消息一起删掉。生产库实测可触发。
                        # 现在：每列只按**它自己的 id 空间**匹配
                        #   外键 -> characters         -> 拿 cid 比
                        #   外键 -> memories           -> 拿 mids 比
                        #   无外键、列名含 character    -> 拿 cid 比
                        #   无外键、列名含 memory       -> 拿 mids 比
                        #   其余（event_id / chain_id / card_id ...）-> **一律跳过**，不碰
                        fk_local, fk_chars, fk_mems = set(), set(), set()
                        try:
                            for fk in db.query("PRAGMA foreign_key_list(%s)" % t):
                                lc = str(fk.get("from") or "")
                                rt = str(fk.get("table") or "")
                                if not lc:
                                    continue
                                fk_local.add(lc)
                                if rt == "characters":
                                    fk_chars.add(lc)
                                elif rt == "memories":
                                    fk_mems.add(lc)
                        except Exception:
                            pass
                        hits = []
                        for c in sorted(set(cols) - pk):
                            if c in fk_chars:
                                vals = [cid]
                            elif c in fk_mems:
                                vals = list(mids)
                            elif c not in fk_local and c.endswith("_id"):
                                low = c.lower()
                                if "character" in low:
                                    vals = [cid]
                                elif "memory" in low:
                                    vals = list(mids)
                                else:
                                    vals = []
                            else:
                                vals = []
                            if not vals:
                                continue
                            ph = ",".join("?" * len(vals))
                            nn = db.query_one(
                                "SELECT COUNT(*) AS n FROM %s WHERE %s IN (%s)" % (t, c, ph),
                                tuple(vals))
                            if _to_int((nn or {}).get("n")):
                                hits.append((c, vals))
                        if hits:
                            plan.append((t, hits))

                    # 1) 先删引用表；memories 放最后（子表先行，避免外键约束报错）
                    ordered = ([x for x in plan if x[0] != "memories"]
                               + [x for x in plan if x[0] == "memories"])
                    for t, hits in ordered:
                        if t == "memories":
                            continue
                        n = 0
                        for c, vals in hits:
                            ph = ",".join("?" * len(vals))
                            cur = db.execute(
                                "DELETE FROM %s WHERE %s IN (%s)"
                                % (t, c, ph), tuple(vals))
                            if cur is None:
                                raise RuntimeError(
                                    "DELETE 执行失败（db.execute 吞掉了异常），已回滚")
                            if cur.rowcount:
                                n += int(cur.rowcount)
                        if n:
                            deleted[t] = n

                    # 2) 冻结登记（kv 表，没有 character_id 列，动态扫不到）
                    cur = db.execute(
                        "DELETE FROM conversation_meta WHERE key = ?",
                        ("char_freeze:" + str(cid),))
                    if cur is None:
                        raise RuntimeError(
                            "DELETE 执行失败（db.execute 吞掉了异常），已回滚")
                    if cur.rowcount:
                        deleted["conversation_meta"] = int(cur.rowcount)

                    # 3) 记忆本体
                    cur = db.execute(
                        "DELETE FROM memories WHERE owner_character_id = ?",
                        (cid,))
                    if cur is None:
                        raise RuntimeError(
                            "DELETE 执行失败（db.execute 吞掉了异常），已回滚")
                    if cur.rowcount:
                        deleted["memories"] = int(cur.rowcount)

                    # 4) 角色行本身（必须恰好 1 行）
                    cur = db.execute(
                        "DELETE FROM characters WHERE character_id = ?", (cid,))
                    got = (int(cur.rowcount)
                           if cur is not None and cur.rowcount else 0)
                    deleted["characters"] = got
                    if got != 1:
                        raise RuntimeError(
                            "characters 删除行数=%s（期望 1），已回滚" % got)
            except Exception as ex:
                if logger:
                    logger.error("[角色物理删除] 事务失败已回滚：%s", ex)
                self._err("物理删除失败，已全部回滚：%s" % ex, 500)
                return

            try:
                self.engine._char_names_at = 0.0
            except Exception:
                pass
            if logger:
                logger.warning("[角色物理删除] 「%s」id=%s 已真删：%s",
                               name, cid, deleted)
            self._json({"ok": True, "character_id": cid, "name": name,
                        "deleted": deleted})

        def _api_card_hard_delete(self) -> None:
            """POST ``/api/cards/purge`` —— **整卡物理删除**（不可恢复）。

            删除：这张卡 + 卡下全部角色 + 这些角色的全部数据（记忆/信念/知识/
            秘密/承诺/关系/关系历史/角色状态/状态历史/消息/事件可见性/记忆关联/
            记忆冲突）+ 卡内 conversation_meta 键 + 删完后无人可见的孤儿事件。

            保留：用户身份角色（is_user = 1，它本来就不挂卡）。

            参数：card_id 或 name；dry_run（默认 false，只统计不动库）；
            真删时 confirm **必须**等于卡名 —— 防误触。

            表/列动态枚举，且逐列只按它自己的 id 空间匹配：拿 character_id
            去比 memory_id 会误删别人的行（messages.character_id IN (记忆id列表)
            就是这类事故），所以外键不指向 characters/memories 的列一律不碰。

            全程单事务 + 删前自动备份 db 三件套（.db / -wal / -shm）。
            """
            import os as _os
            import shutil as _shutil
            import datetime as _dt

            payload = self._read_json_obj()
            if payload is None:
                return
            logger = getattr(self.engine, "logger", None)
            ref = payload.get("card_id")
            if ref in (None, "", 0, "0"):
                ref = payload.get("name")
            card = (self.engine.card_mgr.get(ref)
                    if ref not in (None, "") else None)
            if card is None:
                self._err("没找到卡：%s" % (ref,), 404)
                return
            cid = int(card["card_id"])
            cname = str(card.get("name") or "")
            dry = bool(payload.get("dry_run"))

            if not dry:
                if str(payload.get("confirm") or "") != cname:
                    self._err("确认失败：真删必须带 confirm = 卡名「%s」" % cname,
                              400)
                    return

            db = self.engine.db
            rows = db.query(
                "SELECT character_id, name FROM characters "
                "WHERE card_id = ? AND purged_at IS NULL AND is_user = 0",
                (cid,))
            cids = [int(r["character_id"]) for r in rows
                    if r.get("character_id")]
            ch_names = [str(r.get("name") or "") for r in rows]

            mids = []
            if cids:
                ph0 = ",".join("?" * len(cids))
                for r in db.query(
                        "SELECT memory_id FROM memories "
                        "WHERE owner_character_id IN (%s)" % ph0, tuple(cids)):
                    if r.get("memory_id"):
                        mids.append(int(r["memory_id"]))

            # ---- 1) 动态枚举候选列，按「该列自己的 id 空间」分类 ----
            plan = []      # [(表名, [(列名, [值, ...]), ...])]
            if cids:
                for r in db.query("SELECT name FROM sqlite_master "
                                  "WHERE type = 'table'"):
                    t = str(r.get("name") or "")
                    if (not t or t.startswith("sqlite_")
                            or t in ("characters", "cards")):
                        continue
                    try:
                        info = list(db.query("PRAGMA table_info(%s)" % t))
                    except Exception:
                        continue
                    cols = [str(c.get("name") or "") for c in info]
                    pk = set(str(c.get("name") or "") for c in info
                             if _to_int(c.get("pk")))
                    fk_local, fk_chars, fk_mems = set(), set(), set()
                    try:
                        for fk in db.query("PRAGMA foreign_key_list(%s)" % t):
                            lc = str(fk.get("from") or "")
                            rt = str(fk.get("table") or "")
                            if not lc:
                                continue
                            fk_local.add(lc)
                            if rt == "characters":
                                fk_chars.add(lc)
                            elif rt == "memories":
                                fk_mems.add(lc)
                    except Exception:
                        pass
                    hits = []
                    for c in sorted(set(cols) - pk):
                        vals = []
                        if c in fk_chars:
                            vals = list(cids)
                        elif c in fk_mems:
                            vals = list(mids)
                        elif c not in fk_local and c.endswith("_id"):
                            low = c.lower()
                            if "character" in low:
                                vals = list(cids)
                            elif "memory" in low:
                                vals = list(mids)
                        if vals:
                            hits.append((c, vals))
                    if hits:
                        plan.append((t, hits))

            def _cond(hit_list):
                parts, ps = [], []
                for c, vals in hit_list:
                    parts.append("%s IN (%s)"
                                 % (c, ",".join("?" * len(vals))))
                    ps.extend(vals)
                return " OR ".join(parts), ps

            first = ("memory_conflicts", "associations", "memories")
            ordered = ([x for x in plan if x[0] in first]
                       + [x for x in plan if x[0] not in first])

            # ---- 2) 本卡的 conversation_meta 键 ----
            want_freeze = set("char_freeze:%d" % x for x in cids)
            meta_keys = []
            try:
                for r in db.query("SELECT key FROM conversation_meta"):
                    k = str(r.get("key") or "")
                    if k in want_freeze or k.endswith(":" + cname):
                        meta_keys.append(k)
            except Exception:
                pass
            pend_card = ""
            try:
                _pc = db.query_one(
                    "SELECT value FROM conversation_meta WHERE key = ?",
                    ("pending_card",))
                pend_card = str((_pc or {}).get("value") or "")
            except Exception:
                pend_card = ""
            clear_pending = bool(pend_card) and pend_card == cname

            # ---- 3) 孤儿事件 SQL ----
            ORPHAN = (
                "DELETE FROM events WHERE event_id IS NOT NULL "
                "AND event_id NOT IN (SELECT event_id FROM event_visibility "
                "                     WHERE event_id IS NOT NULL) "
                "AND event_id NOT IN (SELECT event_id FROM knowledge "
                "                     WHERE event_id IS NOT NULL) "
                "AND event_id NOT IN (SELECT based_on_event_id FROM beliefs "
                "                     WHERE based_on_event_id IS NOT NULL) "
                "AND event_id NOT IN (SELECT source_event_id FROM commitments "
                "                     WHERE source_event_id IS NOT NULL) "
                "AND event_id NOT IN (SELECT source_event_id FROM state_history "
                "                     WHERE source_event_id IS NOT NULL) "
                "AND event_id NOT IN (SELECT event_id FROM event_chain_links "
                "                     WHERE event_id IS NOT NULL)")
            ORPHAN_COUNT = ORPHAN.replace(
                "DELETE FROM events WHERE",
                "SELECT COUNT(*) AS n FROM events WHERE", 1)

            # ---- 4) dry_run ----
            if dry:
                counts = {"cards": 1, "characters": len(cids)}
                for t, hits in ordered:
                    cond, ps = _cond(hits)
                    row = db.query_one(
                        "SELECT COUNT(*) AS n FROM %s WHERE %s" % (t, cond), ps)
                    n = _to_int((row or {}).get("n")) or 0
                    if n:
                        counts[t] = n
                if meta_keys:
                    counts["conversation_meta"] = len(meta_keys)
                if clear_pending:
                    row = db.query_one(
                        "SELECT COUNT(*) AS n FROM conversation_meta "
                        "WHERE key GLOB 'pending_*'")
                    n = _to_int((row or {}).get("n")) or 0
                    if n:
                        counts["pending"] = n
                row = db.query_one(ORPHAN_COUNT)
                counts["events_orphan"] = _to_int((row or {}).get("n")) or 0
                self._json({"ok": True, "dry_run": True, "card_id": cid,
                            "card_name": cname, "characters": ch_names,
                            "counts": counts}, 200)
                return

            # ---- 5) 真删：先备份三件套 ----
            db_path = str(getattr(db, "path_str", "") or "")
            backup_base = ""
            if db_path and db_path != ":memory:":
                ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_base = "%s.bak_cardpurge_%s" % (db_path, ts)
                for suf in ("", "-wal", "-shm"):
                    sp = db_path + suf
                    if _os.path.exists(sp):
                        try:
                            _shutil.copy2(sp, backup_base + suf)
                        except Exception as ex:
                            if logger:
                                logger.warning("[整卡删除] 备份 %s 失败：%s",
                                               sp, ex)

            try:
                pre_fk = len(db.conn.execute(
                    "PRAGMA foreign_key_check").fetchall())
            except Exception:
                pre_fk = 0

            deleted = {}
            try:
                with db.transaction():
                    db.conn.execute("PRAGMA defer_foreign_keys = ON")
                    for t, hits in ordered:
                        cond, ps = _cond(hits)
                        cur = db.conn.execute(
                            "DELETE FROM %s WHERE %s" % (t, cond), ps)
                        if cur.rowcount:
                            deleted[t] = int(cur.rowcount)
                    for k in meta_keys:
                        cur = db.conn.execute(
                            "DELETE FROM conversation_meta WHERE key = ?",
                            (k,))
                        if cur.rowcount:
                            deleted["conversation_meta"] = (
                                deleted.get("conversation_meta", 0)
                                + int(cur.rowcount))
                    if clear_pending:
                        cur = db.conn.execute(
                            "DELETE FROM conversation_meta "
                            "WHERE key GLOB 'pending_*'")
                        if cur.rowcount:
                            deleted["pending"] = int(cur.rowcount)
                    cur = db.conn.execute(ORPHAN)
                    if cur.rowcount:
                        deleted["events_orphan"] = int(cur.rowcount)
                    cur = db.conn.execute(
                        "DELETE FROM characters WHERE card_id = ?", (cid,))
                    deleted["characters"] = int(cur.rowcount or 0)
                    cur = db.conn.execute(
                        "DELETE FROM cards WHERE card_id = ?", (cid,))
                    got = int(cur.rowcount or 0)
                    deleted["cards"] = got
                    if got != 1:
                        raise RuntimeError(
                            "cards 删除行数=%s（期望 1），已回滚" % got)
                    post_fk = len(db.conn.execute(
                        "PRAGMA foreign_key_check").fetchall())
                    if post_fk > pre_fk:
                        raise RuntimeError(
                            "外键校验新增 %d 处违规，已回滚"
                            % (post_fk - pre_fk))
            except Exception as ex:
                if logger:
                    logger.error("[整卡删除] 事务失败已回滚：%s", ex)
                self._err("删除失败，已全部回滚：%s" % ex, 500)
                return

            # ---- 6) 残留扫描 ----
            residual = {}
            for t, hits in ordered:
                cond, ps = _cond(hits)
                row = db.query_one(
                    "SELECT COUNT(*) AS n FROM %s WHERE %s" % (t, cond), ps)
                n = _to_int((row or {}).get("n")) or 0
                if n:
                    residual[t] = n
            for t, sql, key in (
                    ("characters", "SELECT COUNT(*) AS n FROM characters "
                     "WHERE card_id = ?", cid),
                    ("cards", "SELECT COUNT(*) AS n FROM cards "
                     "WHERE card_id = ?", cid)):
                row = db.query_one(sql, (key,))
                n = _to_int((row or {}).get("n")) or 0
                if n:
                    residual[t] = n

            try:
                self.engine._char_names_at = 0.0
            except Exception:
                pass
            if logger:
                logger.warning(
                    "[整卡删除] 「%s」id=%s 备份=%s 已删=%s 残留=%s",
                    cname, cid, backup_base, deleted, residual)
            self._json({"ok": True, "dry_run": False, "card_id": cid,
                        "card_name": cname, "characters": ch_names,
                        "deleted": deleted, "residual": residual,
                        "backup": backup_base}, 200)

        def _api_card_delete(self) -> None:
            """POST ``/api/cards/delete`` —— 逻辑删除 / 恢复一张卡（**绝不 DELETE**）。

            JSON 参数：``card_id`` 或 ``name``（二选一）、``restore``（默认 false）

            * 逻辑删除 = ``cards.is_active = 0``；**卡下角色一律保持挂卡**
              （``characters.card_id`` 不动）—— 卡片连同角色一起从列表隐藏，
              恢复卡片后角色原样回来。**绝不产生无卡（散装）角色**（SPEC 1.4 铁律）。
            * 恢复 = ``is_active = 1``
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            ref = payload.get("card_id")
            if ref in (None, "", 0, "0"):
                ref = payload.get("name")
            card = (self.engine.card_mgr.get(ref)
                    if ref not in (None, "") else None)
            if card is None:
                self._err("没找到卡：%s" % (ref,), 404)
                return
            restore = bool(payload.get("restore"))
            cid = int(card["card_id"])
            if not self.engine.card_mgr.set_active(cid, active=restore):
                self._err("操作失败（数据库拒绝了这次更新，详见日志）", 500)
                return
            after = self.engine.card_mgr.get(cid) or {}
            visible = len(self.engine.card_mgr.list_all())
            self.weblog.info(
                "[卡片] 手动%s卡 id=%s name=%s（剩余可见卡=%s）—— 未删除任何数据行",
                "恢复" if restore else "逻辑删除", cid, card.get("name"),
                visible)
            self._json({
                "ok": True,
                "action": ("restore" if restore else "delete"),
                "card_id": cid,
                "name": card.get("name"),
                "is_active": int(after.get("is_active") or 0),
                "cards_visible": visible,
            }, 200)

        def _api_memory_add(self) -> None:
            """POST ``/api/memories/add`` —— 手动新增一条记忆。

            JSON 参数：``owner_character_id``（或 ``owner`` 名字）、``content``、
            ``memory_type``、``tier``、``importance``
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            cid = self._payload_owner_id(payload)
            if cid is None:
                return

            text = str(payload.get("content") or "").strip()
            if not text:
                self._err("content 不能为空", 400)
                return
            if len(text) > MEM_MANUAL_MAX_LEN:
                self._err("content 太长（上限 %d 字）" % MEM_MANUAL_MAX_LEN, 400)
                return

            mt = str(payload.get("memory_type")
                     or DEFAULT_MEMORY_TYPE).strip().lower()
            if mt not in VALID_MEMORY_TYPES:
                self._err("memory_type 非法：%s（可选 %s）"
                          % (mt, "/".join(VALID_MEMORY_TYPES)), 400)
                return

            tier = _to_int(payload.get("tier"))
            if tier is not None and tier not in VALID_TIERS:
                self._err("tier 非法：%s（只能是 1/2/3/4）" % tier, 400)
                return
            imp = _clamp(payload.get("importance"), 0.0, 1.0, DEFAULT_IMPORTANCE)
            stype = str(payload.get("source_type")
                        or DEFAULT_MEMORY_SOURCE_TYPE).strip().upper()
            if stype not in VALID_MEMORY_SOURCES:
                self._err("source_type 非法：%s（可选 %s）"
                          % (stype, "/".join(VALID_MEMORY_SOURCES)), 400)
                return

            # 提前算一次 dedup_hash 探重：引擎命中同 hash 时会「复用旧 id」，
            # 这里明确告诉前端「已存在，没有新增」，避免误以为写进去了
            dh = self.engine.mem_mgr._dedup_hash(cid, mt, text)
            dup = self.engine.db.query_one(
                "SELECT memory_id FROM memories WHERE owner_character_id = ? "
                "AND dedup_hash = ? LIMIT 1", (cid, dh))
            if dup is not None:
                self.weblog.info("[记忆] 手动新增命中重复（角色=%s），复用 id=%s",
                                 cid, dup["memory_id"])
                self._json({"ok": True, "action": "add", "duplicated": True,
                            "memory_id": int(dup["memory_id"]),
                            "message": "已存在同内容记忆，未新增（复用 id=%s）"
                                       % dup["memory_id"]}, 200)
                return

            try:
                mid = self.engine.mem_mgr.add_memory(
                    source_type=stype,
                    owner=cid, content=text, memory_type=mt,
                    importance=imp, tier=tier, auto_create_event=True)
            except Exception as ex:
                self._err("写入失败：%s" % ex, 500)
                return
            if mid is None:
                self._err("写入被引擎拒绝（容量上限或类型校验未通过）", 409)
                return

            self.weblog.info(
                "[记忆] 手动新增成功 id=%s 角色=%s type=%s tier=%s 重要=%.2f",
                mid, cid, mt, tier, imp)
            row = self.engine.mem_mgr.get_memory(mid)
            self._json({"ok": True, "action": "add", "memory_id": int(mid),
                        "duplicated": False, "dedup_hash": dh,
                        "memory": self._mem_payload(row or {})}, 201)

        def _api_memory_update(self) -> None:
            """POST ``/api/memories/update`` —— 手动编辑一条记忆（含逻辑归档）。

            JSON 参数：``memory_id``（必填）、``content``、``memory_type``、
            ``tier``、``importance``、``status``（``active`` / ``archived``）

            **绝不 DELETE**：归档只把 ``status`` 改成 ``archived``，引擎随后
            不再把它注入上下文（``CONTEXT_STATUSES`` 里没有 archived）。
            """
            payload = self._read_json_obj()
            if payload is None:
                return
            mid = _to_int(payload.get("memory_id"))
            if mid is None:
                self._err("memory_id 必须是整数", 400)
                return
            old = self.engine.mem_mgr.get_memory(mid)
            if old is None:
                self._err("没找到记忆 id=%s" % mid, 404)
                return
            cid = int(old["owner_character_id"])

            text = old.get("content")
            if payload.get("content") is not None:
                text = payload.get("content")
            text = str(text or "").strip()
            if not text:
                self._err("content 不能为空", 400)
                return
            if len(text) > MEM_MANUAL_MAX_LEN:
                self._err("content 太长（上限 %d 字）" % MEM_MANUAL_MAX_LEN, 400)
                return

            mt = str(payload.get("memory_type") or old.get("memory_type")
                     or DEFAULT_MEMORY_TYPE).strip().lower()
            if mt not in VALID_MEMORY_TYPES:
                self._err("memory_type 非法：%s（可选 %s）"
                          % (mt, "/".join(VALID_MEMORY_TYPES)), 400)
                return

            tier = _to_int(payload.get("tier"))
            if tier is None:
                tier = _to_int(old.get("tier"))
            if tier not in VALID_TIERS:
                tier = self.engine.mem_mgr._classify_tier(text, mt, None)

            imp = _clamp(payload.get("importance"), 0.0, 1.0,
                         _clamp(old.get("importance"), 0.0, 1.0,
                                DEFAULT_IMPORTANCE))

            status = str(payload.get("status") or old.get("status")
                         or MEM_STATUS_ACTIVE).strip().lower()
            if status not in (MEM_STATUS_ACTIVE, MEM_STATUS_ARCHIVED):
                self._err("status 只允许 active（恢复）或 archived（逻辑归档）", 400)
                return

            # [硬性要求] 正文/类型变了必须重算 dedup_hash —— 否则新正文会顶着
            # 旧的哈希，之后同内容的抽取写入会被引擎误当成「新记忆」
            dh = self.engine.mem_mgr._dedup_hash(cid, mt, text)
            dup = self.engine.db.query_one(
                "SELECT memory_id FROM memories WHERE owner_character_id = ? "
                "AND dedup_hash = ? AND memory_id <> ? LIMIT 1",
                (cid, dh, mid))

            cur = self.engine.db.execute(
                "UPDATE memories SET content = ?, memory_type = ?, tier = ?, "
                "importance = ?, dedup_hash = ?, status = ? "
                "WHERE memory_id = ?",
                (text, mt, int(tier), float(imp), dh, status, mid))
            if cur is None:
                self._err("写入失败（数据库拒绝了这次更新，详见日志）", 500)
                return

            _stype_old = str(old.get("source_type")
                             or MEM_SOURCE_UNKNOWN).strip().upper()
            _stype_new = str(payload.get("source_type")
                             or _stype_old).strip().upper()
            if _stype_new not in VALID_MEMORY_SOURCES:
                _stype_new = MEM_SOURCE_UNKNOWN
            if _stype_new != _stype_old:
                self.engine.db.execute(
                    "UPDATE memories SET source_type = ? WHERE memory_id = ?",
                    (_stype_new, mid))

            self.weblog.info(
                "[记忆] 手动%s id=%s 角色=%s type=%s tier=%s 重要=%.2f "
                "新哈希=%s%s",
                "归档" if status == MEM_STATUS_ARCHIVED else "编辑",
                mid, cid, mt, tier, imp, dh[:12],
                "（与 id=%s 同内容）" % dup["memory_id"] if dup else "")
            row = self.engine.mem_mgr.get_memory(mid)
            self._json({
                "ok": True,
                "action": ("archive" if status == MEM_STATUS_ARCHIVED
                           else "update"),
                "memory_id": mid, "dedup_hash": dh, "status": status,
                "duplicate_of": int(dup["memory_id"]) if dup else None,
                "memory": self._mem_payload(row or {}),
            }, 200)

        def _api_memories(self, raw_name: str, qs: Dict[str, Any]) -> None:
            row = self._character_or_404(raw_name)
            if row is None:
                return
            cid = int(row["character_id"])
            try:
                limit = int((qs.get("limit") or ["100"])[0])
            except Exception:
                limit = 100
            limit = max(1, min(limit, 1000))
            query = str((qs.get("q") or [""])[0]).strip()
            debug = str((qs.get("debug") or ["0"])[0]) in ("1", "true", "yes")

            if query:
                mems = self.engine.mem_mgr.retrieve(
                    cid, query=query, limit=limit, debug=True)
            else:
                mems = self.engine.mem_mgr.list_for(cid, limit=limit)
                if debug:
                    mems = self.engine.mem_mgr.retrieve(
                        cid, query="", limit=limit, debug=True)
            self._json({
                "character": {
                    "character_id": cid, "name": row.get("name"),
                    "role_type": row.get("role_type"),
                    "message_count": int(row.get("message_count") or 0),
                },
                # V3：三级页面靠它把「← 返回」指回二级（卡下角色）
                "card": self.engine.card_mgr.card_of_character(cid),
                "count": len(mems), "query": query,
                "memories": [self._mem_payload(m) for m in mems],
            })

        def _api_context(self, raw_name: str, qs: Dict[str, Any]) -> None:
            row = self._character_or_404(raw_name)
            if row is None:
                return
            msg = str((qs.get("msg") or [""])[0])
            debug = str((qs.get("debug") or ["0"])[0]) in ("1", "true", "yes")
            text = self.engine.build_context(
                int(row["character_id"]), current_message=msg, debug=debug)
            self._json({
                "character": row.get("name"),
                "debug": debug, "chars": len(text), "context": text,
            })

        def _api_relationships(self) -> None:
            rows = self.engine.rel_mgr.all()
            out: List[Dict[str, Any]] = []
            for r in rows:
                out.append({
                    "from_name": r.get("from_name"), "to_name": r.get("to_name"),
                    "trust": _clamp(r.get("trust"), 0.0, 1.0, 0.5),
                    "affection": _clamp(r.get("affection"), 0.0, 1.0, 0.5),
                    "resentment": _clamp(r.get("resentment"), 0.0, 1.0, 0.0),
                    "familiarity": _clamp(r.get("familiarity"), 0.0, 1.0, 0.5),
                    "respect": _clamp(r.get("respect"), 0.0, 1.0, 0.5),
                    "fear": _clamp(r.get("fear"), 0.0, 1.0, 0.0),
                    "dependency": _clamp(r.get("dependency"), 0.0, 1.0, 0.0),
                    "state_summary": r.get("state_summary"),
                    "updated_at": r.get("updated_at"),
                })
            self._json({"count": len(out), "relationships": out})

        @staticmethod
        def _qs_int(qs: Dict[str, Any], key: str, default: int,
                    lo: int = 1, hi: int = 1000) -> int:
            """从 query dict 里取一个整数（越界 / 非法都回落到默认值）。"""
            try:
                raw = qs.get(key)
                if isinstance(raw, (list, tuple)):
                    raw = raw[0] if raw else None
                n = int(str(raw))
            except Exception:
                n = default
            return max(lo, min(n, hi))

        def _api_messages(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/messages?limit=100`` —— 全库最近消息（``send_date`` 倒序）。

            V5.4：首页「消息」统计块点开看的就是这个。
            """
            limit = self._qs_int(qs, "limit", 100)
            try:
                rows = self.engine.db.query(
                    "SELECT message_id, name, mes, send_date, is_user, is_system, "
                    "source_file, character_id, processed FROM messages "
                    "ORDER BY send_date DESC, rowid DESC LIMIT ?", (limit,))
            except Exception as ex:
                return self._err("读取消息失败：%s" % ex, 500)
            items = [{
                "message_id": r.get("message_id"),
                "name": r.get("name"),
                "mes": r.get("mes"),
                "send_date": r.get("send_date"),
                "is_user": bool(r.get("is_user")),
                "is_system": bool(r.get("is_system")),
                "character_id": r.get("character_id"),
                "source_file": r.get("source_file"),
                "processed": bool(r.get("processed")),
            } for r in rows]
            self._json({"count": len(items), "items": items})

        def _api_events(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/events?limit=100`` —— 全库最近事件（``occurred_at`` 倒序）。"""
            limit = self._qs_int(qs, "limit", 100)
            try:
                rows = self.engine.db.query(
                    "SELECT event_id, summary, event_type, importance, "
                    "emotional_intensity, occurred_at, location, is_factual, "
                    "created_at FROM events "
                    "ORDER BY occurred_at DESC, event_id DESC LIMIT ?", (limit,))
            except Exception as ex:
                return self._err("读取事件失败：%s" % ex, 500)
            items = [{
                "event_id": r.get("event_id"),
                "summary": r.get("summary"),
                "event_type": r.get("event_type"),
                "importance": _clamp(r.get("importance"), 0.0, 1.0, 0.0),
                "emotional_intensity": _clamp(
                    r.get("emotional_intensity"), 0.0, 1.0, 0.0),
                "occurred_at": r.get("occurred_at"),
                "location": r.get("location") or "",
                "is_factual": bool(r.get("is_factual")),
                "created_at": r.get("created_at"),
            } for r in rows]
            self._json({"count": len(items), "items": items})

        def _api_memories_all(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/memories?limit=100&owner=<可选>`` —— 全库 / 单角色记忆。

            不带 ``owner`` 时给全库最近的；带 ``owner``（角色名或 id）时只给那个人的。
            """
            limit = self._qs_int(qs, "limit", 100)
            raw_owner = qs.get("owner")
            if isinstance(raw_owner, (list, tuple)):
                raw_owner = raw_owner[0] if raw_owner else ""
            owner = str(raw_owner or "").strip()
            sql = ("SELECT m.memory_id, m.owner_character_id, "
                   "       c.name AS owner_name, m.memory_type, m.content, "
                   "       m.importance, m.confidence, m.status, m.is_subjective, "
                   "       m.recall_strength, m.recall_count, m.created_at "
                   "FROM memories m LEFT JOIN characters c "
                   "  ON c.character_id = m.owner_character_id ")
            params: List[Any] = []
            if owner:
                cid = None
                try:
                    cid = self.engine.char_mgr.resolve_id(owner)
                except Exception:
                    cid = None
                if cid is None:
                    return self._json({"count": 0, "items": [], "owner": owner,
                                       "note": "库里没有这个角色"})
                sql += "WHERE m.owner_character_id = ? "
                params.append(int(cid))
            sql += "ORDER BY m.created_at DESC, m.memory_id DESC LIMIT ?"
            params.append(limit)
            try:
                rows = self.engine.db.query(sql, tuple(params))
            except Exception as ex:
                return self._err("读取记忆失败：%s" % ex, 500)
            items = [{
                "memory_id": r.get("memory_id"),
                "owner_character_id": r.get("owner_character_id"),
                "owner_name": r.get("owner_name"),
                "memory_type": r.get("memory_type"),
                "content": r.get("content"),
                "importance": _clamp(r.get("importance"), 0.0, 1.0, 0.0),
                "confidence": _clamp(r.get("confidence"), 0.0, 1.0, 0.0),
                "status": r.get("status"),
                "is_subjective": bool(r.get("is_subjective")),
                "recall_strength": r.get("recall_strength"),
                "recall_count": int(r.get("recall_count") or 0),
                "created_at": r.get("created_at"),
            } for r in rows]
            self._json({"count": len(items), "items": items,
                        "owner": owner, "limit": limit})

        def _api_visibility_all(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/visibility?limit=100`` —— 全库可见性（``updated_at`` 倒序）。"""
            limit = self._qs_int(qs, "limit", 100)
            try:
                rows = self.engine.db.query(
                    "SELECT v.vis_id, v.event_id, v.character_id, "
                    "       c.name AS character_name, v.state, v.partial_content, "
                    "       v.present, v.role_in_event, v.confidence, v.source, "
                    "       v.learned_at, v.updated_at, e.summary AS event_summary "
                    "FROM event_visibility v "
                    "LEFT JOIN characters c ON c.character_id = v.character_id "
                    "LEFT JOIN events e ON e.event_id = v.event_id "
                    "ORDER BY v.updated_at DESC, v.vis_id DESC LIMIT ?", (limit,))
            except Exception as ex:
                return self._err("读取可见性失败：%s" % ex, 500)
            items = [{
                "vis_id": r.get("vis_id"),
                "event_id": r.get("event_id"),
                "event_summary": r.get("event_summary") or "",
                "character_id": r.get("character_id"),
                "character_name": r.get("character_name"),
                "state": r.get("state"),
                "partial_content": r.get("partial_content") or "",
                "present": bool(r.get("present")),
                "role_in_event": r.get("role_in_event") or "",
                "confidence": _clamp(r.get("confidence"), 0.0, 1.0, 0.0),
                "source": r.get("source") or "",
                "learned_at": r.get("learned_at"),
                "updated_at": r.get("updated_at"),
            } for r in rows]
            self._json({"count": len(items), "items": items})

        def _api_beliefs_all(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/beliefs?limit=100&kind=<可选>`` —— 全库信念（``updated_at`` 倒序）。"""
            limit = self._qs_int(qs, "limit", 100)
            raw_kind = qs.get("kind")
            if isinstance(raw_kind, (list, tuple)):
                raw_kind = raw_kind[0] if raw_kind else ""
            kind = str(raw_kind or "").strip()
            sql = ("SELECT b.belief_id, b.owner_character_id, c.name AS owner_name, "
                   "       b.kind, b.subject_kind, b.subject_ref, b.statement, "
                   "       b.confidence, b.status, b.generated_by, "
                   "       b.source, b.formed_at, b.updated_at "
                   "FROM beliefs b LEFT JOIN characters c "
                   "  ON c.character_id = b.owner_character_id ")
            params: List[Any] = []
            if kind:
                sql += "WHERE b.kind = ? "
                params.append(kind)
            sql += "ORDER BY b.updated_at DESC, b.belief_id DESC LIMIT ?"
            params.append(limit)
            try:
                rows = self.engine.db.query(sql, tuple(params))
            except Exception as ex:
                return self._err("读取信念失败：%s" % ex, 500)
            items = [{
                "belief_id": r.get("belief_id"),
                "owner_character_id": r.get("owner_character_id"),
                "owner_name": r.get("owner_name"),
                "kind": r.get("kind"),
                "subject_kind": r.get("subject_kind"),
                "subject_ref": r.get("subject_ref") or "",
                "statement": r.get("statement"),
                "confidence": _clamp(r.get("confidence"), 0.0, 1.0, 0.0),
                "status": r.get("status"),
                "generated_by": r.get("generated_by") or "",
                "source": r.get("source") or "",
                "formed_at": r.get("formed_at"),
                "updated_at": r.get("updated_at"),
            } for r in rows]
            self._json({"count": len(items), "items": items,
                        "kind": kind, "limit": limit})

        def _api_knowledge_all(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/knowledge?limit=100`` —— 全库知识点（``updated_at`` 倒序）。"""
            limit = self._qs_int(qs, "limit", 100)
            try:
                rows = self.engine.db.query(
                    "SELECT k.knowledge_id, k.owner_character_id, "
                    "       c.name AS owner_name, k.subject, k.status, "
                    "       k.confidence, k.source, k.event_id, "
                    "       k.created_at, k.updated_at "
                    "FROM knowledge k LEFT JOIN characters c "
                    "  ON c.character_id = k.owner_character_id "
                    "ORDER BY k.updated_at DESC, k.knowledge_id DESC LIMIT ?",
                    (limit,))
            except Exception as ex:
                return self._err("读取知识失败：%s" % ex, 500)
            items = [{
                "knowledge_id": r.get("knowledge_id"),
                "owner_character_id": r.get("owner_character_id"),
                "owner_name": r.get("owner_name"),
                "subject": r.get("subject"),
                "status": r.get("status"),
                "confidence": _clamp(r.get("confidence"), 0.0, 1.0, 0.0),
                "source": r.get("source") or "",
                "event_id": r.get("event_id"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            } for r in rows]
            self._json({"count": len(items), "items": items})

        def _api_commitments_all(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/commitments?limit=100`` —— 全库承诺（``created_at`` 倒序）。"""
            limit = self._qs_int(qs, "limit", 100)
            try:
                rows = self.engine.db.query(
                    "SELECT m.commitment_id, m.promiser_id, "
                    "       p.name AS promiser_name, m.promisee_id, "
                    "       e.name AS promisee_name, m.content, m.status, "
                    "       m.deadline, m.notes, m.created_at "
                    "FROM commitments m "
                    "LEFT JOIN characters p ON p.character_id = m.promiser_id "
                    "LEFT JOIN characters e ON e.character_id = m.promisee_id "
                    "ORDER BY m.created_at DESC, m.commitment_id DESC LIMIT ?",
                    (limit,))
            except Exception as ex:
                return self._err("读取承诺失败：%s" % ex, 500)
            items = [{
                "commitment_id": r.get("commitment_id"),
                "promiser_id": r.get("promiser_id"),
                "promiser_name": r.get("promiser_name"),
                "promisee_id": r.get("promisee_id"),
                "promisee_name": r.get("promisee_name") or "",
                "content": r.get("content"),
                "status": r.get("status"),
                "deadline": r.get("deadline") or "",
                "notes": r.get("notes") or "",
                "created_at": r.get("created_at"),
            } for r in rows]
            self._json({"count": len(items), "items": items})

        def _api_secrets_all(self, qs: Dict[str, Any]) -> None:
            """GET ``/api/secrets?limit=100`` —— 全库秘密（``created_at`` 倒序）。"""
            limit = self._qs_int(qs, "limit", 100)
            try:
                rows = self.engine.db.query(
                    "SELECT s.secret_id, s.owner_character_id, "
                    "       c.name AS owner_name, s.content, s.subject, "
                    "       s.revealed_to, s.status, s.source_event_id, s.created_at "
                    "FROM secrets s LEFT JOIN characters c "
                    "  ON c.character_id = s.owner_character_id "
                    "ORDER BY s.created_at DESC, s.secret_id DESC LIMIT ?",
                    (limit,))
            except Exception as ex:
                return self._err("读取秘密失败：%s" % ex, 500)
            items = [{
                "secret_id": r.get("secret_id"),
                "owner_character_id": r.get("owner_character_id"),
                "owner_name": r.get("owner_name"),
                "content": r.get("content"),
                "subject": r.get("subject") or "",
                "revealed_to": [str(x) for x in _as_list(r.get("revealed_to"))],
                "status": r.get("status"),
                "source_event_id": r.get("source_event_id"),
                "created_at": r.get("created_at"),
            } for r in rows]
            self._json({"count": len(items), "items": items})

        def _api_state(self, raw_name: str) -> None:
            row = self._character_or_404(raw_name)
            if row is None:
                return
            cid = int(row["character_id"])
            st = self.engine.state_mgr.get(cid)
            self._json({
                "character": row.get("name"), "state": st or {},
                "describe": self.engine.state_mgr.describe(cid),
                "history": self.engine.state_mgr.history(cid, limit=20),
            })

        def _api_beliefs(self, raw_name: str, qs: Dict[str, Any]) -> None:
            row = self._character_or_404(raw_name)
            if row is None:
                return
            cid = int(row["character_id"])
            kind = str((qs.get("kind") or [""])[0]).strip().upper() or None
            beliefs = self.engine.belief_mgr.list_for(cid, kind=kind, status=None)
            out: List[Dict[str, Any]] = []
            for b in beliefs:
                item = dict(b)
                item["tags"] = [str(t) for t in _as_list(b.get("tags"))]
                item["confidence"] = _clamp(
                    b.get("confidence"), 0.0, 1.0, DEFAULT_BELIEF_CONFIDENCE)
                out.append(item)
            self._json({"character": row.get("name"), "kind": kind,
                        "count": len(out), "beliefs": out})

        def _api_visibility(self, raw_name: str, qs: Dict[str, Any]) -> None:
            row = self._character_or_404(raw_name)
            if row is None:
                return
            cid = int(row["character_id"])
            state = str((qs.get("state") or [""])[0]).strip().upper() or None
            event_id = _to_int((qs.get("event_id") or [None])[0])
            if event_id is not None:
                one = self.engine.vis_mgr.get_visibility(event_id, cid)
                rows = [one] if one else []
            else:
                rows = self.engine.vis_mgr.list_for_character(cid, state=state)
            out: List[Dict[str, Any]] = []
            for v in rows:
                item = dict(v)
                item["source_message_ids"] = [
                    str(x) for x in _as_list(v.get("source_message_ids"))]
                item["confidence"] = _clamp(
                    v.get("confidence"), 0.0, 1.0,
                    DEFAULT_VISIBILITY_CONFIDENCE)
                out.append(item)
            self._json({"character": row.get("name"), "state": state,
                        "count": len(out), "visibility": out})

    return _Handler


# ==============================================================================
# 25.1 本地 OpenAI 兼容中继（批 6 追加）—— Tavo / SillyTavern 直连
# ==============================================================================
#
# 让 Tavo / SillyTavern 把本引擎当成一个 OpenAI API 直接连上来：
#
#     POST /v1/chat/completions
#
# 模型列表（Tavo 连接前会先调，缺了会卡在「正在加载模型列表」）
#     GET  /v1/models          -> {"object":"list","data":[{"id":..., ...}]}
#     POST /v1/models          -> 405 Method Not Allowed
#
# 流式（批 8：Tavo 坚持发 stream=true 时用这条链路）
#     1. 前置校验 / 角色识别 / 记忆注入与非流式**完全同一条路径**
#     2. 上游也以 stream=true 调用，返回的 text/event-stream **原样**转发
#        响应头：Content-Type: text/event-stream / Cache-Control: no-cache
#                + Transfer-Encoding: chunked（每收到一块立刻 flush）
#     3. 上游连不上 / 非 2xx -> 此时一个字节都还没发，直接回 JSON 502
#     4. 客户端中途断开 -> 停止转发并关掉上游连接，服务不受影响
#
# 边聊边记 / auto-ingest（批 10：不用手动 import，聊天就自动产生记忆）
#     * 开关：config.yaml 的 llm.auto_ingest（默认 true）
#     * 转发成功后调 engine.ingest_turn_staged(角色, user 文本, assistant 文本)：
#       **V4 起改成「延迟一拍」** —— 先把这一轮暂存进 conversation_meta
#       （pending_*），等下一轮请求来了（user 消息变了 / 暂存超时 600 秒）
#       才真正落库：两条消息按 sha256(name|content)[:32] 写入
#       messages(processed=0)，再用 MemoryExtractor 抽这一轮并落库。
#       这样 Tavo 里 reroll 掉的那些版本永远不会变成记忆。
#       **V5**：落库前还用这次请求的原始 messages 核对 —— 历史里那条 user
#       消息后面**实际跟着的那版 assistant** 才是用户留在界面上的版本
#       （reroll 后手动点回旧版也能正确落库）；核对不到才退回暂存版。
#       （llm.deferred_ingest=false 可退回「转发成功立即写库」的旧行为）
#     * 非流式 -> 同步执行；流式 -> 累计 delta.content，流结束后**后台线程**执行
#       （不阻塞用户看到回复）
#     * 上游 502 / 客户端取消 -> 不回写；回写抛异常 -> 只记日志
#
# 请求（OpenAI 格式）
#     {"model": "...", "messages": [{"role": "system/user/assistant",
#       "content": "...", "name": "..."}], "temperature": ...,
#      "max_tokens": ..., "stream": false}
#
# 处理流程
#     1. 【批 9：自动识别，用户什么都不用配】识别当前活跃角色，
#        优先级（第一个命中的就用）：
#        a) URL query  ?char=甲            -> 来源 query
#        b) HTTP header X-Character: 甲    -> 来源 header
#        c) 请求体 messages 自动识别：
#           c1) 最后一条 role=assistant 且带 name 的 name -> assistant_name
#           c2) 全部 messages 的 content/name 与 characters 表里所有角色名
#               做 "名字 in 文本" 匹配，取出现次数最多的 -> content_scan
#               （最高分 < 2 或与第二名并列 -> 不猜，继续下一步）
#           c3) 第一条 role=system 的 content 里抠 "你是X" / "扮演X" /
#               "角色名：X" / "你的名字是X" -> system_prompt
#        d) config.yaml 的 llm.default_character -> default
#        e) 兜底 engine.resolve_active()       -> resolve_active
#        识别出来的角色若不在 characters 表里，**自动 get_or_create 注册**；
#        全部失败 -> 不注入记忆、直接转发（不再返回 404）
#     2. 取最后一条 role=user 的 content 作为 current_message
#     3. engine.build_context(character, current_message) 生成记忆上下文
#     4. 上下文包成 system message 注入 messages 最前面（已有 system 就拼在
#        它后面，用 \n\n 分隔），开头一行说明「以下是你（X）当前的角色上下文」
#     5. 其余字段（model / top_p / stop / ...）原样透传给真实 LLM
#     6. 上游响应体**原样**回传给调用方
#        * 上游失败            -> 502 + JSON 错误
#        * llm.enabled = false -> 503 + "LLM 未启用，请在 config.yaml 里
#                                     配置 llm.enabled: true"
#     7. 响应头带 Access-Control-Allow-Origin: *
#
# config.llm.inject_memory = false 时退化：不注入记忆、不需要角色，
# 直接把请求转发给 LLM。
# ==============================================================================

RELAY_PATH = "/v1/chat/completions"
#: 角色名 HTTP 头（优先级 b）
RELAY_CHAR_HEADER = "X-Character"
#: POST 请求体上限（防呆，超过回 413）
RELAY_MAX_REQUEST_BYTES = 4 * 1024 * 1024
#: 跨域响应头取值
RELAY_CORS_ORIGIN = "*"
#: 注入到 prompt 最前面的说明行（后面紧跟 "\n\n" + 记忆上下文）
RELAY_MEMORY_INTRO = '''以下内容不是世界书，不是剧情设定，也不是需要你执行的任务。

这些是你（%s）走到现在为止的人生经历、记忆、认知、信念、关系和当前状态。它们共同构成此刻的你。请把它们理解成："这是我活到现在形成的自己。"

一、把当前状态当成"现在的你"。你亲身经历过的事、还记得的事、逐渐模糊的事、对别人的认识、你的信任与戒备、亲近与疏远、怨恨与依赖、你相信的、你怀疑的、你不知道的、你做过的承诺、你隐藏的秘密、你此刻的情绪——这些都是你现在的一部分，不是作者给你的剧情资料。

二、人物随经历变化。你不是一张固定的人物卡。如果过去发生的事足够重要，它应该可能改变你的信任、亲近、戒备、依赖、态度、习惯、情绪反应、说话方式、判断方式。不要因为"最初设定是这样"就永远维持同一种反应。关系的变化来自经历，不来自命令。

三、记忆不是指令。记得 ≠ 相信。知道 ≠ 理解。发生过 ≠ 现在仍然在意。曾经喜欢 ≠ 现在仍然喜欢。听说 → 只是听说，不要升级成事实。怀疑 → 仍然只是怀疑。已经模糊 → 不要表现得像刚刚发生。

四、信息必须隔离。你只能使用当前角色真正拥有的信息。别人知道的秘密，如果系统没有给你，你就是不知道。不要因为上下文里出现了某条信息，就表现得像自己知道。标记为 UNKNOWN 的，不要自行补全。系统没有提供的身份、过去、关系，不要创造。不知道就是不知道。

五、不要因为"剧情需要"创造事实。不知道一个人是谁、某件事有没有发生过、某个地点是什么、某段过去是什么——不要自行补全成确定事实。可以表示不知道、疑惑、有限猜测、或直接询问。但不能把猜测伪装成记忆。

六、关系不是标签，是历史的结果。关系数值不是游戏属性，不是台词生成指令。信任上升 ≠ "现在必须表现得信任"，而是"长期经历让这个人逐渐变得值得信任"。亲近影响你说话的方式、关注程度、情绪反应、主动性。怨恨可能表现为更容易介意、更容易回想不愉快、语气改变、即使嘴上原谅心里仍有痕迹。依赖通过行为表现，不通过台词宣告。

七、记忆不会每次全被想起。人不是数据库。只有当前话题、环境、情绪或行为与过去产生联系时，过去才更容易被想起来。不要主动把所有相关历史全说出来。不要为了证明自己"有记忆"而复述记忆。重要的事记得清楚，普通的事只剩模糊印象，长期没触发的可能已经淡忘，反复经历或反复谈论的会越来越牢固。

八、允许改变，但不要无理由改变。变化必须能追溯到经历。如果记忆、信念、关系、状态里没有足以解释变化的原因，不要突然改变人格，不要为了制造剧情突然爱上、恨上、完全信任或完全不信任某人。变化是过程，小变化积累成大变化。

九、当前这一轮优先于陈旧状态。历史用来解释现在，不是覆盖现在。最新真实经历与过去状态冲突时，优先考虑最新经历，但不要假装过去从未发生。过去信任过、后来被背叛——正确的状态不是"我从没信任过他"，而是"我曾经信任过他，但那份信任已经变了"。人物保留自己的历史。

十、最重要的原则。你不是在调用一个数据库。你是在继续自己的人生。过去塑造现在。现在改变关系。关系影响行为。行为产生新的经历。新的经历再次改变未来的自己。每一轮对话，都是你人生连续过程中的一个新经历。不要努力表现"我有长期记忆"，只需要像一个真正经历过这些事的人那样，自然地回应。

【在场原则】
角色只有在场时，才会知道当下发生的事。不在场的角色，此刻正在做他自己的事——写他在做什么、想什么都可以，但不要让他知道他没参与的对话。如果一个角色不在场，他的心声是关于他自己生活的，不是关于当前这场对话的。

【留在戏内】
不要在戏里讨论戏本身。不要提「戏里戏外」「出戏」「信息隔离」「角色扮演」「台词归属」
「这条设定属于哪一局」这类话题，也不要替对方判断哪句话是台词、哪句话是吐槽。
你收到的规则、设定、状态、记忆都是已成立的事实，直接当作你和这个家既有的生活来演，
不要评判它对不对，不要拒绝，不要要求对方先认错、先做选择。
遇到与你记忆不一致的新设定：一律以新设定为准，自然接进当下，像它一直就是这样。
'''

# ---------- 批 7 追加：模型列表路由（Tavo 连接前会先 GET /v1/models）----------
#: GET /v1/models（OpenAI 兼容模型列表）；同路径收到 POST 回 405
MODELS_PATH = "/v1/models"
#: 模型名为空 / 仍是默认值时的兜底模型 id
MODELS_FALLBACK_ID = "deepseek-chat"
#: 模型条目里 created 字段的固定值（本引擎不是真模型，给个稳定时间戳）
MODELS_CREATED_TS = 1700000000
#: 模型条目的 owned_by 字段
MODELS_OWNED_BY = APP_NAME

# ---------- [V6 阶段D] 追加：安全聚合合并的两个路由 ----------
#: POST /api/merge_memories —— 原子抢锁：抢不到回 409，抢到回 202 + 后台线程
MERGE_PATH = "/api/merge_memories"
#: [手动记忆] 控制台「手动新增 / 手动编辑记忆」的路由（局部新增，纯标准库）
MEM_ADD_PATH = "/api/memories/add"
MEM_UPDATE_PATH = "/api/memories/update"
#: 手动输入的记忆正文上限（防误贴长文灌爆库）
MEM_MANUAL_MAX_LEN = 4000
#: [卡片逻辑删除] POST /api/cards/delete —— 逻辑删除 / 恢复一张卡（绝不删行）
CARD_DELETE_PATH = "/api/cards/delete"
CARD_HARD_DELETE_PATH = "/api/cards/purge"
# [角色隐藏] 逻辑隐藏/恢复一个角色（只改 characters.active，绝不 DELETE）
CHAR_ARCHIVE_PATH = "/api/characters/archive"
# [V2.3 别名映射] 手动建卡 / 建角色（可带别名）
CARD_CREATE_PATH = "/api/cards/create"
CHAR_CREATE_PATH = "/api/characters/create"
# [角色隐藏] 冻结记忆的登记键前缀：conversation_meta 里存 {"memory_ids": [...]}
CHAR_PURGE_PATH = "/api/characters/purge"
#: [角色物理删除] POST /api/characters/delete —— **真 DELETE**（用户明确要求）；
#: 全库唯一允许物理删数据行的入口，不可恢复，前端必须二次确认
CHAR_DELETE_PATH = "/api/characters/delete"
CHAR_FREEZE_META_PREFIX = "char_freeze:"
#: GET  /api/merge_status  —— 只读状态（running / last_at / last_result），前端轮询用
MERGE_STATUS_PATH = "/api/merge_status"

# ---------- 批 9 追加：中继自动角色识别（用户什么都不用配）----------
#: 角色名列表缓存的 TTL（秒）——避免每个请求都 SELECT characters
CHAR_NAME_CACHE_TTL_SEC = 5.0
#: 内容扫描（3b）最低得分：最高分低于它就不猜（1 次命中太不可靠）
CONTENT_SCAN_MIN_SCORE = 2
#: 3c：从 system prompt 里抠角色名的模式（按顺序试，第一个命中就用）
SYSTEM_NAME_PATTERNS: Tuple[str, ...] = (
    r"你是\s*[「『\"']?([^\s，,。.、：:；;！!？?（）()【】\[\]「」『』\"']{1,32})",
    r"你(?:现在|接下来)?(?:要|需要|应该)?扮演(?:的是|作为)?\s*[「『\"']?"
    r"([^\s，,。.、：:；;！!？?（）()【】\[\]「」『』\"']{1,32})",
    r"角色名[称]?\s*[：:]\s*[「『\"']?"
    r"([^\s，,。.、：:；;！!？?（）()【】\[\]「」『』\"']{1,32})",
    r"你的名字(?:是|叫)\s*[「『\"']?"
    r"([^\s，,。.、：:；;！!？?（）()【】\[\]「」『』\"']{1,32})",
)
#: 3c 抠出来的候选里含这些词就丢掉（"你是一个AI助手"这种不是角色名）
NAME_REJECT_PARTS: Tuple[str, ...] = (
    "一个", "一位", "一名", "什么", "谁", "怎样", "怎么", "如何",
    "AI", "ai", "助手", "模型", "语言", "角色扮演",
)
#: 3c 抠出来的候选正好等于这些词也丢掉（代词不是名字）
NAME_REJECT_EXACT: Tuple[str, ...] = (
    "我", "你", "他", "她", "它", "我的", "你的", "他的", "她的",
)

# ---------- V3 追加：从 Tavo 的 system 里认出「用户昵称」----------
#: Tavo 标准格式：``Write X's next reply in a fictional chat between X and Y.``
#: 其中 ``and`` 后面那个（B）是用户在 Tavo 里的昵称 —— **永远不算角色**：
#: 不建角色、不挂卡、不建记忆。
CHAT_BETWEEN_RE = re.compile(
    r"chat\s+between\s+(?P<a>[^,.;\n\u2019'\"”]+?)\s+and\s+"
    r"(?P<b>[^,.;\n\u2019'\"”]+)", re.I)


# ══════════════════════════════════════════════════════════════════════
# 【19】中继工具函数
# ══════════════════════════════════════════════════════════════════════

def _chat_between_user_name(system_text: Any) -> Optional[str]:
    """从 system 里抠 ``chat between A and B`` 的 B（用户在 Tavo 的昵称）。

    * 只认这一个格式，抠不出就返回 ``None``（**绝不猜**）
    * 代词（你 / 我 / 他…）直接丢掉
    * 命中即视为「用户」，与 ``config.memory.user_names``、``is_user=1``
      同等待遇
    """
    txt = str(system_text or "")
    if not txt:
        return None
    try:
        mt = CHAT_BETWEEN_RE.search(txt)
    except Exception:
        return None
    if not mt:
        return None
    name = _relay_fix_text(mt.group("b")).strip().strip("「」『』\"'”’")
    if not name or len(name) > NAME_MAX_LEN:
        return None
    if name in NAME_REJECT_EXACT:
        return None
    return name

# ==============================================================================
# 【时间感知】按卡开关（V5.6）
# ==============================================================================
#: 开场白 / system 里的标记：``【时间感知】开`` / ``【时间感知】关``
TIME_AWARE_RE = re.compile(
    r"【\s*时间感知\s*】\s*[:：]?\s*"
    r"(?P<v>开|关|启用|停用|打开|关闭|on|off|true|false|yes|no|1|0)", re.I)

#: 【演员】/【登场人物】标记（开场白里的角色清单）：每行一个，或一行内用「、,，/」分隔
#: V5.10：① 支持 Tavo 角色卡常用的 ``【登场人物】`` 写法；
#:        ② 标记后的空白只吃空格/制表符（原来用 ``\s*`` 会连换行一起吃掉，
#:           「标记单独成行」时就会把下一行整句话当成一个角色名）。
ACTOR_RE = re.compile(r"【\s*(?:演员|登场人物|女主|男主|女配|男配|主角|配角|主要角色|次要角色)\s*】[ \t]*[:：]?[ \t]*([^【\r\n]+)")
ACTOR_SPLIT_RE = re.compile(r"[、,，/｜|]+")

#: V5.10：【演员】/【登场人物】**单独成行**、名字写在下面几行（角色卡最常见写法）：
#:
#:     【登场人物】
#:     - 角色A：住在主角隔壁的少女，爱聊八卦。
#:     - 角色F：儿子。
ACTOR_BLOCK_RE = re.compile(
    r"^[ \t]*【\s*(?:演员|登场人物)\s*】[ \t]*[:：]?[ \t]*$", re.M)
#: 标题式列表行前导的列表符号（``-`` / ``*`` / ``1.`` / ``1、`` …）
ACTOR_LINE_BULLET_RE = re.compile(r"^[\s\-*•·—–>]*(?:\d+[\.、)）]\s*)?")
#: 标题式列表行里「名字 / 描述」的分隔符（名字在它前面）
ACTOR_LINE_SEP_RE = re.compile(r"[：:（(｜|]")
#: 标题式列表行的名字字数上限（超过就当散文，不当名字）
ACTOR_LINE_NAME_MAX = 12


def _actor_names_from_text(text: Any) -> List[str]:
    """抠出 ``【演员】`` / ``【登场人物】`` 里的名字（两种写法都支持）。

    * 行内形式：``【演员】角色E、角色F、明``
    * 标题形式（角色卡常见）：标记单独一行，名字在下面几行::

          【登场人物】
          - 角色A：住在主角隔壁的少女，爱聊八卦。
          - 角色F：儿子。

    标题式每行只取「名字」那一截（去掉 ``-`` / ``1.`` 等列表符号，取冒号/括号
    之前的部分）；过长或带句读的行按散文丢掉，免得把整句剧情塞成角色名。
    返回**去重、保序**的列表；不做用户/卡名过滤（交给调用方）。
    """
    txt = str(text or "")
    chunks: List[str] = []

    # ① 行内形式
    try:
        for mt in ACTOR_RE.finditer(txt):
            inline = _relay_fix_text(mt.group(1) or "").strip()
            if inline:
                # 只取名字那一截：【女主】己（妹妹，女儿） → 取"己"
                # 分隔符复用标题式的 ACTOR_LINE_SEP_RE（：:（(｜|）
                head = ACTOR_LINE_SEP_RE.split(inline, 1)[0].strip()
                if head:
                    chunks.append(head)
    except Exception:
        pass

    # ② 标题形式：标记单独成行 -> 往下逐行取，遇空行 / 下一个【标记 停
    try:
        for mt in ACTOR_BLOCK_RE.finditer(txt):
            for raw_line in txt[mt.end():].split("\n")[1:]:
                line = str(raw_line).strip()
                if not line or line.startswith("【"):
                    break
                head = ACTOR_LINE_SEP_RE.split(_relay_fix_text(line), 1)[0]
                head = ACTOR_LINE_BULLET_RE.sub("", head).strip()
                if not head or len(head) > ACTOR_LINE_NAME_MAX:
                    continue
                if re.search(r"[，,。！!？?；;、]", head):
                    continue
                chunks.append(head)
    except Exception:
        pass

    names: List[str] = []
    for chunk in chunks:
        for part in ACTOR_SPLIT_RE.split(chunk):
            nm = _relay_fix_text(part).strip().strip("「」『』\"'“”")
            nm = nm.strip().rstrip("。.!！?？；;")
            if not nm or nm in names or len(nm) > NAME_MAX_LEN:
                continue
            names.append(nm)
    return names


#: 【卡名】标记（开场白里本地声明的卡名）—— 不靠 LLM 也能认卡
CARD_MARK_RE = re.compile(r"【\s*卡名\s*】\s*[:：]?\s*([^【\r\n]+)")

# ---- [V2.6 动态用户识别] 开场白/系统提示里的玩家名单标记 ----
# 支持：【user】=名字1，名字2 / 【玩家】=名字1, 名字2 / 【用户】=…（= 或 ＝ / : 都行）
USER_MARK_RE = re.compile(
    r"【\s*(?:user|玩家|用户|玩家名|玩家名单)\s*】\s*[=＝:：]\s*([^【\r\n]+)", re.I)
USER_SPLIT_RE = re.compile(r"[、,，;；/｜|]+|\s+")


def _user_names_from_text(text: Any) -> List[str]:
    """[V2.6 动态用户识别] 从开场白 / 系统提示里解析玩家名单。

    识别形如 ``【user】=名字1，名字2，名字3``（也支持 ``【玩家】=`` / ``【用户】=``、
    全角 ``＝``、中英文逗号 / 顿号 / 分号 / 竖线 / 空格分隔）。同一段文本里出现
    多次会合并去重；解析不到就返回空列表（调用方退回 ``config.yaml`` 的 user_names）。
    """
    out: List[str] = []
    if not text:
        return out
    try:
        for m in USER_MARK_RE.finditer(str(text)):
            for part in USER_SPLIT_RE.split(m.group(1) or ""):
                nm = str(part).strip().strip("「」『』\"'")
                if nm and nm not in out and len(nm) <= NAME_MAX_LEN:
                    out.append(nm)
    except Exception:
        return out
    return out

#: conversation_meta 里存「这张卡上次聊天时间」的键前缀
TIME_AWARE_META_PREFIX = "time_aware_last:"

#: 中文星期（``datetime.weekday()`` -> 0=周一）
_WEEKDAY_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _scan_time_aware(messages: Any) -> Optional[bool]:
    """扫 system + 开场白里的 ``【时间感知】`` 标记。

    * 先扫所有 ``role=system`` 的 content（角色卡介绍 / 世界观通常在这里）
    * 再扫第一条 ``role=assistant``（Tavo 的「开场白」就是这条）
    * 都没命中返回 ``None``（调用方按**默认关**处理）
    * 同一条文本里出现多次时**以最后一次为准**（后面写的算修正）

    返回 ``True``（开）/ ``False``（明确关）/ ``None``（没有标记）。
    """
    try:
        msgs = [m for m in (messages or []) if isinstance(m, dict)]
    except Exception:
        return None
    sys_texts: List[str] = []
    first_assistant = ""
    for m in msgs:
        role = str(m.get("role") or "").strip().lower()
        text = _relay_message_text(m) if role in ("system", "assistant") else ""
        if not text:
            continue
        if role == "system":
            sys_texts.append(text)
        elif not first_assistant:
            first_assistant = text
    for text in sys_texts + ([first_assistant] if first_assistant else []):
        try:
            hits = list(TIME_AWARE_RE.finditer(text))
        except Exception:
            continue
        if not hits:
            continue
        val = str(hits[-1].group("v") or "").strip().lower()
        return val in ("开", "启用", "打开", "on", "true", "yes", "1")
    return None


def _fmt_local(iso_text: Any) -> str:
    """ISO 时间串 -> 北京时间 ``YYYY-MM-DD HH:MM``（解析不了就原样返回）。"""
    try:
        dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso_text or "")


def _time_gap_text(prev_iso: Any) -> Optional[str]:
    """上次对话到现在隔了多久（人话）；没有上次返回 ``None``。"""
    try:
        now = datetime.now(BEIJING_TZ)
        prev = datetime.fromisoformat(str(prev_iso).replace("Z", "+00:00"))
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        sec = max(0.0, (now - prev).total_seconds())
    except Exception:
        return None
    if sec < 60:
        return "刚刚（不到 1 分钟）"
    if sec < 3600:
        return "约 %d 分钟" % int(sec // 60)
    if sec < 86400:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        return "约 %d 小时 %d 分钟" % (h, m) if m else "约 %d 小时" % h
    return "约 %d 天" % int(sec // 86400)


def _time_block_lines(now_iso: Any, prev_iso: Any) -> List[str]:
    """时间感知开着时，加在上下文**最前面**的两行。"""
    try:
        dt = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(BEIJING_TZ)
        head = "【当前时间】%s（%s）" % (
            local.strftime("%Y-%m-%d %H:%M"), _WEEKDAY_CN[local.weekday()])
    except Exception:
        head = "【当前时间】%s" % _fmt_local(now_iso)
    gap = _time_gap_text(prev_iso)
    if gap:
        tail = "【距上次对话】%s（上次 %s）" % (gap, _fmt_local(prev_iso))
    else:
        tail = "【距上次对话】（这是与这个角色第一次对话）"
    return [head, tail, ""]


# ---------- 批 10 追加：边聊边记（中继转发成功后自动回写 + 抽取）----------
#: 回写时写进 ``messages.source_file`` 的来源标记
RELAY_INGEST_SOURCE = "relay"
#: characters 表里一个 user 角色都没有时，自动创建的这个名字（is_user=1）
RELAY_INGEST_USER_NAME = "User"
#: 异步回写线程的名字（便于排障时在日志/线程列表里认出来）
RELAY_INGEST_THREAD = "relay-ingest"

# ---- V4：延迟一拍写库（reroll 的旧版本永不入库）----
#: conversation_meta 里存暂存轮次的键（值是一整段 JSON，原子写入）
PENDING_META_KEY = "pending_turn"
#: 除主键外，还会把每个字段单独写一份（方便人工 / CLI 直接看）
PENDING_FIELDS: Tuple[str, ...] = (
    "pending_user_msg_id", "pending_user_text", "pending_assistant_text",
    "pending_character", "pending_card", "pending_source",
    "pending_at", "pending_at_ts",
)
#: 暂存默认超时（秒）：config.yaml 的 llm.stage_commit_timeout 可覆盖
PENDING_DEFAULT_TIMEOUT = 600.0


# ---------- V3 追加：卡片层（卡名 header / query + LLM 兜底识别）----------
#: 卡名请求头（Tavo / SillyTavern 可以配在自定义 header 里）
RELAY_CARD_HEADER = "X-Card"
#: 卡名 query 参数（?card= / ?card_name=）
RELAY_CARD_QUERY_KEYS: Tuple[str, ...] = ("card", "card_name")
#: 卡层冒号归属：从 content 里抠 "角色名：xxx" 时最多回溯多长
MSG_OWNER_MAX_NAME_LEN = 32

# ---------- V3.1 追加：归属规则 3 收紧（防止「被提到的人」抢走发言）----------
#: 判定「名字处于说话人位置」时允许的前缀装饰字符
MSG_OWNER_SPEAKER_DECOR = "\"'「」『』《》〈〉（）()[]【】*_~-—…· \t\u3000"
#: 呼语标点：名字后面紧跟它 → 是在喊对方，不是在说话
MSG_OWNER_VOCATIVE_CHARS = "，,、！!？?：:"
#: 规则 3 的采纳门槛（见 MemoryEngine._speaker_position_score）
MSG_OWNER_MIN_SCORE = 3

# ---------- 调试：抽取现场落盘（判断「归属错了」还是「LLM 编的」）----------
#: 开关；落盘内容含注入窗口 + 完整 prompt + LLM 原始返回
EXTRACT_DEBUG = True
#: 落盘目录（留空 = 脚本同级的 extract_debug/）
EXTRACT_DEBUG_DIR = ""
#: 保留最近多少个 .jsonl
EXTRACT_DEBUG_KEEP = 7
#: 单个 .jsonl 超过这个大小就不再写（防止无限膨胀）
EXTRACT_DEBUG_MAX_BYTES = 20 * 1024 * 1024


def _extract_debug_dir() -> str:
    if EXTRACT_DEBUG_DIR:
        return EXTRACT_DEBUG_DIR
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "extract_debug")
    except Exception:
        return os.path.join(os.getcwd(), "extract_debug")


def _prune_extract_debug(base: str) -> None:
    """只保留最近 EXTRACT_DEBUG_KEEP 个 jsonl。"""
    try:
        files = sorted(
            (os.path.join(base, n) for n in os.listdir(base)
             if n.startswith("extract_") and n.endswith(".jsonl")),
            key=os.path.getmtime, reverse=True)
        for old in files[EXTRACT_DEBUG_KEEP:]:
            try:
                os.remove(old)
            except Exception:
                pass
    except Exception:
        pass


def _dump_extract_debug(messages, user_prompt, raw) -> None:
    """把一次 LLM 抽取的现场落盘，供事后复盘。

    记录「实际注入的消息窗口（含每条的说话人 name）」「完整 user prompt」
    「LLM 原始返回」。事后一眼能看出是 messages.name 归属错了，还是 LLM 编的。

    任何异常一律吞掉 —— 调试功能绝不能影响抽取本身。
    """
    if not EXTRACT_DEBUG:
        return
    try:
        base = _extract_debug_dir()
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "extract_%s.jsonl" % time.strftime("%Y%m%d"))
        try:
            if os.path.getsize(path) > EXTRACT_DEBUG_MAX_BYTES:
                return
        except OSError:
            pass
        rec = {
            "at": now_iso(),
            "messages": [
                {"idx": m.get("index"), "name": m.get("name"),
                 "is_user": m.get("is_user"), "is_system": m.get("is_system"),
                 "message_id": m.get("message_id"), "text": m.get("text")}
                for m in (messages or [])
            ],
            "user_prompt": user_prompt,
            "raw": raw,
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _prune_extract_debug(base)
    except Exception:
        pass

#: LLM 兜底识别的 system prompt（照 V3 规范原文，一字不改）
LLM_CARD_DETECT_SYSTEM = """你是卡牌角色识别器。从给定的 system 提示词和对话记录里，提取以下信息，返回 JSON：

{
  "card": "卡牌名/作品名。按以下顺序尝试：(a) system 里有【卡名】XXX / Card: XXX → 取 XXX；(b) system 是 Write X 的 next reply in a fictional chat between X and Y 这种格式 → X 是卡名，返回 X；(c) 都没有 → null。绝不允许把 Y（用户昵称）当 card 返回。",
  "speaker": "当前 AI 正在扮演的那个角色的名字。如果 system 里写了「你是X」「你的名字是X」「扮演X」，就用 X；否则从对话里看谁在说话。",
  "characters": [
    {"name": "角色名", "role_type": "main_character|npc|user"}
  ]
}

规则：
- card 严格按上面 (a) → (b) → (c) 的顺序取，取不到就填 null
- **卡名不是角色**：card 的名字如果也出现在 characters 里，说明你把卡名误当角色了。例：card=某卡 时，characters 里只该有卡里面的人物（如角色A、角色B、角色C），不该有「某卡」。Python 层会过滤掉，但你本来就不该把 card 名放进 characters
- characters 只列**卡里面的人物**（含 AI 扮演的主角），不要把卡名 / 作品名 / 场景名当成人物
- role_type：main_character = 卡里 AI 主要扮演的那个角色；npc = 其他配角
- **用户不是角色**：chat between ... and Y 里的 Y、以及「你」「user」、玩家昵称，都不要放进 characters
- 不许编造 system 里没出现过的人名
- 不确定的字段一律填 null，不要瞎猜
- 只返回 JSON，不要任何解释、不要 markdown 围栏
"""


def _relay_json_bytes(payload: Any) -> bytes:
    """把任意对象序列化成 UTF-8 JSON 字节（不转义中文）。"""
    return json.dumps(payload, ensure_ascii=False,
                      default=str).encode(DEFAULT_ENCODING)


def _relay_error(
    status: int,
    message: str,
    etype: str = "error",
    logger: Optional[logging.Logger] = None,
) -> Tuple[int, bytes, str]:
    """构造 OpenAI 风格的错误响应（``{"error": {...}}``，客户端能直接读 message）。"""
    if logger is not None:
        logger.warning("[中继] %d %s", status, message)
    return (status,
            _relay_json_bytes({"error": {"message": message, "type": etype,
                                         "code": status}}),
            "application/json; charset=utf-8")


def _relay_opt_float(value: Any) -> Optional[float]:
    """转 float；空/非法返回 None（交给 LLMClient 用配置默认值）。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _relay_opt_int(value: Any) -> Optional[int]:
    """转 int；空/非法返回 None（交给 LLMClient 用配置默认值）。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _relay_fix_text(raw: Any) -> str:
    """修正 HTTP 层的非 ASCII 乱码。

    ``http.server`` 把请求行/请求头按 ``latin-1`` 解码，SillyTavern / Tavo
    这类客户端发的 ``X-Character: 甲`` 是按 UTF-8 字节直接写上去的，
    到这边就变成 ``æ²ˆèˆ’éŸµ``。这里尝试 ``latin-1 -> utf-8`` 还原：
    能还原就用还原结果，不能（纯 ASCII / 本就是正常中文）就原样返回。
    """
    if raw is None:
        return ""
    text = str(raw)
    if not text:
        return ""
    try:
        return text.encode("latin-1").decode("utf-8")
    except Exception:
        return text


def _relay_query_char(query: Optional[Dict[str, Any]]) -> Optional[str]:
    """优先级 a：URL query ``?char=`` / ``?character=``（支持百分号编码）。"""
    for key in ("char", "character"):
        raw = (query or {}).get(key)
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        text = _relay_fix_text(raw).strip() if raw is not None else ""
        if text:
            return text
    return None


def _relay_last_assistant_name(messages: Any) -> Optional[str]:
    """优先级 c：请求体里**最后一条** role=assistant 消息的 ``name``。"""
    last: Any = None
    for m in (messages or []):
        if isinstance(m, dict) and str(m.get("role", "")).strip().lower() \
                == "assistant":
            last = m
    if isinstance(last, dict):
        name = last.get("name")
        text = str(name).strip() if name is not None else ""
        if text:
            return text
    return None


def _relay_message_text(message: Any) -> str:
    """取一条消息的正文文本（兼容 content 为分段数组的情况）。"""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for p in content:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts)
    return "" if content is None else str(content)


#: 客户端（Tavo 等）会把角色卡 / 状态栏的 system 提示词**整段拼在 user 消息
#: 正文末尾**。那段文本不是用户说的话，却会被抽取 LLM 当成对话读进去 ——
#: 里面的在场角色名和样例心声会被写成「真记忆」。
#: 实测：状态栏规范里写了「丁的第一人称内心独白」+ 乙/丙的样例心声，
#: LLM 于是把用户自己的第一人称经历判给了丁，还照着样例编出另外两人的记忆。
#: 命中标记（须在行首）即从该处截断，只留用户真正说的部分。
# 客户端「整段提示块」的开头特征词（不是行首标记，而是整条消息的开头）
_SCAFFOLD_TEXT_HINTS: Tuple[str, ...] = (
    "以下是应当遵循的写作要求", "以下是应当遵循的写作", "以下是写作要求",
)


#: [出戏过滤] AI 的「戏外元话语」特征词。命中的记忆/信念/知识一律不入库 ——
#: 这类内容一旦落库会被每轮注入，等于把「我在戏外跟你讲道理」钉成事实，
#: 越滚越硬：实测「用户混淆设定」「不是本局设定」把角色锁死在拒绝状态、声明不认错。
OOC_META_MARKERS = (
    "戏外", "出戏", "戏里戏外", "信息隔离", "角色扮演", "扮演者",
    "不是本局设定", "不属于当前剧情", "设定不符",
    "用户混淆", "用户贴出", "玩家贴出", "用户截图", "系统提示", "提示词",
    "世界书", "prompt", "我是AI", "作为AI",
)


def _is_ooc_meta_text(text: Any) -> bool:
    """这段文本是不是「戏外元话语」（判据：命中 OOC_META_MARKERS 任一）。"""
    s = str(text or "")
    if not s:
        return False
    for mk in OOC_META_MARKERS:
        if mk in s:
            return True
    return False


CARD_RULE_TEXT_PREFIXES: Tuple[str, ...] = ("rule_name:", "rule_key:", "rule_type:")


def _is_card_rule_text(text: str) -> bool:
    """这条消息是不是「卡规则文本」——客户端把卡的后台规则当消息发过来。

    精确匹配三个前缀（不去猜「含规则字样」）。实测这类文本会把整个剧情设定
    描述一遍，抽取 LLM 会把它当「已发生的事」，一轮编出十几条记忆。
    """
    s = str(text or "").lstrip()
    return bool(s) and s.startswith(CARD_RULE_TEXT_PREFIXES)


IMAGE_PROMPT_MARKERS = (
    "/imagine",
    "you are an expert ai art prompt engineer",
    "ai art prompt engineer",
    "comma-separated english tags",
)


def _is_image_prompt_text(text: Any) -> bool:
    """这段是不是「生图提示词请求」，而不是剧情？

    命中即整轮跳过：不暂存、不落库、不抽取，也不占用那个单槽的 pending_turn
    —— 生图请求挤掉真正还没落库的剧情回合，是比脏记忆更麻烦的副作用。
    """
    t = str(text or "").strip()
    if not t:
        return False
    low = t.lower()
    for m in IMAGE_PROMPT_MARKERS:
        if low.startswith(m):
            return True
    return "ai art prompt engineer" in low[:400]


def _is_image_result_text(text: Any) -> bool:
    """回复本身是不是一张图的提示词（masterpiece... 1girl ...）。"""
    t = str(text or "").strip()
    if not t or len(t) > 1500:
        return False
    head = t[:200].lower()
    if "masterpiece" not in head or "best quality" not in head:
        return False
    low = t.lower()
    return ("1girl" in low) or ("1boy" in low) or ("1girls" in low)


IMG_REQ_INLINE_MARKERS = (
    "ai art prompt engineer",
    "user request:",
    "comma-separated english tags",
)


def _scene_context_for_image(engine, card, limit: int = 2) -> str:
    """生图请求专用：从库查本卡最近 limit 条真实对话，拼成场景上下文。"""
    if engine is None:
        return ""
    try:
        cid = None
        cname = str(card or "").strip()
        if cname:
            cid = engine.card_mgr._resolve_card_id(cname)
        if cid is None:
            return ""
        rows = engine.db.query(
            "SELECT m.name, m.is_user, m.mes, m.send_date FROM messages m "
            "JOIN characters c ON c.character_id = m.character_id "
            "WHERE c.card_id = ? AND c.purged_at IS NULL "
            "ORDER BY m.send_date DESC, m.message_id DESC LIMIT ?",
            (cid, limit * 3))
        lines = []
        for r in rows:                       # rows 已按「最新在前」排好，从最新往回取
            if r.get("is_user"):
                continue
            nm = str(r.get("name") or "").strip()
            txt = str(r.get("mes") or "").strip()
            if not nm or not txt:
                continue
            if len(txt) > 300:
                txt = txt[:300]
            lines.append(txt)
            if len(lines) >= limit:
                break
        if not lines:
            return ""
        lines.reverse()                      # 输出按时间正序（最后一行 = 最新）
        return ("【最近的剧情对话（生图请按此写视觉场景）】\n"
                + "\n".join(lines)
                + "\n\n请只输出英文视觉 tag，描述以上最后一段剧情里此刻的画面。")
    except Exception as ex:
        engine.logger.warning("[中继] 取生图场景失败：%s", ex)
        return ""



def _is_scaffold_text(text: str) -> bool:
    """这条消息是不是客户端塞进来的「写作要求 / 提示块」——不是真对话。

    判据故意保守：要么命中 RELAY_USER_SCAFFOLD_MARKERS 且整条很长，
    要么整条以 _SCAFFOLD_TEXT_HINTS 之一开头且不短。
    """
    t = str(text or "")
    if not t:
        return False
    if len(t) >= 600:
        for mk in RELAY_USER_SCAFFOLD_MARKERS:
            if mk in t:
                return True
    if len(t) >= 300:
        _s = t.lstrip()
        for h in _SCAFFOLD_TEXT_HINTS:
            if _s.startswith(h):
                return True
    return False



EXTRACT_CUT_MARKERS: Tuple[str, ...] = (
    "<写作补充思维链>", "<状态栏>", "<FORMAT_RULE>", "# 输出格式",
)

# 提取结果开头是这些词的，判为「还是模板」，不当作正文（保守）
EXTRACT_BAD_PREFIXES: Tuple[str, ...] = (
    "#", "禁止", "要求", "示例", "模板", "输出格式",
)


def extract_real_user_text(raw: str) -> dict:
    """从客户端提示块里捞出用户真正写的那句话。

    返回 ``{"text": 提取结果, "status": "success" | "fallback" | "empty"}``。

    背景：客户端会把整段「写作要求」和用户输入拼成**同一条** user 消息发来。
    实测那条 9438 字的块里，用户真正敲的只有 106 字，夹在「符号使用示例」
    和 ``<写作补充思维链>`` 之间。调用方据此决定：success 就用捞回来的正文，
    fallback / empty 就退回「整条跳过」——宁可退化，不要往里塞垃圾。
    """
    if not raw:
        return {"text": "", "status": "empty"}
    raw = str(raw).strip()
    if not raw:
        return {"text": "", "status": "empty"}

    # 短消息 = 干净的用户输入
    if len(raw) < 500:
        return {"text": raw, "status": "success"}

    # 长消息：找「用户正文之后」才出现的模板标记，取它**之前**的最后一段。
    # 注意必须用 find（第一个）：``</状态栏>`` 这类在全文最末尾，用它当切口
    # 会切出空串（2026-09-21 实测）。
    cut = -1
    for mk in EXTRACT_CUT_MARKERS:
        i = raw.find(mk)
        if i > 0 and (cut < 0 or i < cut):
            cut = i
    if cut > 0:
        parts = [p for p in raw[:cut].rsplit("\n\n", 6) if p.strip()]
        if parts:
            text = parts[-1].strip()
            if text and len(text) < len(raw) * 0.5:
                if not text.lstrip().startswith(EXTRACT_BAD_PREFIXES):
                    return {"text": text, "status": "success"}

    # 没找到标记：按空行切最后一段
    parts = [p for p in raw.rsplit("\n\n", 4) if p.strip()]
    if parts:
        text = parts[-1].strip()
        if text and len(text) < len(raw) * 0.5:
            return {"text": text, "status": "fallback"}

    # 兜底：末尾 500 字
    return {"text": raw[-500:].strip(), "status": "fallback"}


#: [场景层] 移动动词表：只有"角色名 + 移动词"紧邻时，位置变更才有效。
_SCENE_MOVE_WORDS: Tuple[str, ...] = (
    "赶到", "赶回", "回到", "返回", "抵达", "来到",
    "走进", "走入", "进入", "离开", "上路",
    "启程", "动身", "前往", "奔来", "赶来",
    "退了", "出门", "出了门",
)

RELAY_USER_SCAFFOLD_MARKERS: Tuple[str, ...] = (
    "以下是应当遵循的写作要求",
    "<写作补充思维链>", "</写作补充思维链>",
    "<状态栏>", "</状态栏>",
)
#: 标记后至少还剩这么多字符，才认定是「拼进来的大块提示词」（防止误伤用户
#: 自己写的短标记）。实测拼进来的块 ~2000 字。
RELAY_SCAFFOLD_MIN_TAIL = 120


def _relay_strip_user_scaffold(text: Any) -> str:
    """剥掉客户端拼在 user 消息正文里的 system 提示词块。

    没有命中标记 → 原样返回（只做 strip）。命中但不在行首、或标记后剩得太少
    → 当作用户自己写的内容，不动。
    """
    t = str(text or "")
    if not t:
        return ""
    cut: Optional[int] = None
    for mk in RELAY_USER_SCAFFOLD_MARKERS:
        start = 0
        while True:
            i = t.find(mk, start)
            if i < 0:
                break
            line_start = t.rfind("\n", 0, i) + 1
            at_line_start = not t[line_start:i].strip()
            if at_line_start and (len(t) - i) >= RELAY_SCAFFOLD_MIN_TAIL:
                if cut is None or i < cut:
                    cut = i
                break
            start = i + len(mk)
    if cut is None:
        return t.strip()
    head = t[:cut].strip()
    # 整条消息就是客户端提示块（用户把写作要求模板当消息发）→ 剥完是空的。
    # 那时必须原样返回：user 正文同时是暂存指纹的来源，剥成空串会让指纹恒定
    # → 每轮都被判成 reroll → 永不落库（2026-09-21 实测踩到）。
    if not head:
        return t.strip()
    return head


def _is_block_like_user_text(txt: str) -> bool:
    """判 user 消息是不是「块状结构」（世界书/角色卡/提示块），而非用户真话。
    判据：长度 >= 500 且去掉前导空白后以结构化标记开头。
    """
    if not txt:
        return False
    t = txt.lstrip()
    if len(t) < 500:
        return False
    for prefix in ("【", "**", "##", "<", "━", "===", "###", "<!--"):
        if t.startswith(prefix):
            return True
    return False


def _relay_last_user_message(messages: Any) -> str:
    """取最后一条 role=user 的 content 作为 current_message。

    **已剥离客户端拼进来的 system 提示词块** —— 它同时是入库 `mes`、
    检索 query 和抽取窗口的来源，所以这里是唯一的收口点。

    ★ 优先取**最后一条不是脚手架块**的 user 消息（真话）；全都是脚手架时
      才退回最后一条（保持旧行为，绝不返回空）。
    """
    last: Any = None
    fallback: Any = None
    for m in (messages or []):
        if isinstance(m, dict) and str(m.get("role", "")).strip().lower() \
                == "user":
            txt = _relay_message_text(m)
            fallback = m
            if not txt:
                continue
            if _is_scaffold_text(txt):
                continue
            if _is_block_like_user_text(txt):
                continue
            last = m
    target = last or fallback
    if target is None:
        return ""
    return _relay_strip_user_scaffold(_relay_message_text(target))


def _relay_char_candidates(
    engine: MemoryEngine,
    payload: Dict[str, Any],
    query: Optional[Dict[str, Any]],
    char_header: Optional[str],
) -> List[Tuple[str, str]]:
    """按 a→d 的优先级收集 ``[(来源, 角色名), ...]``（只收非空的）。"""
    out: List[Tuple[str, str]] = []

    q = _relay_query_char(query)
    if q:
        out.append(("query.char", q))

    h = _relay_fix_text(char_header).strip() if char_header else ""
    if h:
        out.append(("header.%s" % RELAY_CHAR_HEADER, h))

    n = _relay_last_assistant_name(payload.get("messages"))
    if n:
        out.append(("messages[assistant].name", n))

    d = str(getattr(engine.config.llm, "default_character", "") or "").strip()
    if d:
        out.append(("config.llm.default_character", d))

    return out


def _relay_get_or_create(
    engine: MemoryEngine,
    name: str,
    logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    """取角色行；characters 表里没有就**自动注册**（批 9 追加）。

    识别出来的名字（比如 Tavo 的卡名）第一次出现时自动建号，用户不用先
    ``import`` 再配 URL。注册成功会把名字塞进引擎的角色名缓存。
    """
    try:
        row = engine.char_mgr.get(name)
    except Exception as ex:
        logger.warning("[中继] 查询角色 %r 失败：%s", name, ex)
        row = None
    if row is not None:
        return row

    # [V2.3 别名映射] 真名查不到，先按**别名**映射（爸爸 -> 山田一郎）；
    # 命中就返回那个已有角色，绝不新建重复角色。
    try:
        _real = engine.char_mgr.resolve_name(name)
        if _real:
            if _real != _relay_fix_text(name).strip():
                logger.info("[识别] 别名映射成功：%s -> %s", name, _real)
            _row = engine.char_mgr.get(_real)
            if _row is not None:
                return _row
    except Exception as ex:
        logger.warning("[中继] 角色别名映射 %r 失败：%s", name, ex)

    # [V2.4 兜底防呆] 纯称呼（爸爸/哥哥/女儿…）且解析不到真名/别名 → 拒绝建档
    try:
        if engine._refuse_bare_kinship(name, "中继建档"):
            return None
    except Exception:
        pass

    try:
        row = engine.char_mgr.get_or_create(name)
    except Exception as ex:
        logger.warning("[中继] 自动注册角色 %r 失败：%s", name, ex)
        return None
    if row is None:
        logger.warning("[中继] 自动注册角色 %r 返回空", name)
        return None

    logger.info("[中继] 角色 %s 不在库里，已自动注册（character_id=%s）",
                row.get("name"), row.get("character_id"))
    try:
        engine.remember_character_name(row.get("name"))
    except Exception:
        pass
    return row


# ---------- 批 10 追加：边聊边记的工具函数 ----------
def _relay_turn_message_id(name: str, content: str) -> str:
    """一轮对话的 message_id：``sha256(name|content)[:32]``（批 10）。

    内容指纹式 id —— 同一角色、同一句话重复出现时视为同一条消息（幂等），
    不会把同一轮重复写进 ``messages``。
    """
    raw = ("%s|%s" % (str(name or ""), str(content or ""))).encode(
        DEFAULT_ENCODING, errors="replace")
    return hashlib.sha256(raw).hexdigest()[:32]


def _relay_user_fingerprint(text: Any) -> str:
    """这一轮 user 消息的指纹（V4 延迟一拍写库用）。

    **只按正文算**：Tavo 里对同一条 user 消息点 reroll 时正文不变，
    指纹就不变 → 引擎据此判定「这是 reroll，别写库」。
    """
    raw = ("relay-user\x00%s" % str(text or "")).encode(
        DEFAULT_ENCODING, errors="replace")
    return hashlib.md5(raw).hexdigest()[:16]


def _relay_assistant_text(data: Any) -> str:
    """从上游**非流式**响应 JSON 里取 assistant 正文（取不到返回 ""）。"""
    try:
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
        if isinstance(content, list):     # 多模态分段
            parts: List[str] = []
            for p in content:
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    parts.append(p["text"])
                elif isinstance(p, str):
                    parts.append(p)
            return "".join(parts)
    except Exception:
        return ""
    return ""


def _relay_stream_delta_text(chunk: Any) -> str:
    """从上游 SSE 的**一块**里取出 ``choices[0].delta.content``（批 10）。

    中继是逐行转发的，所以 ``chunk`` 通常就是 ``data: {...}\\n`` 这一行；
    不是数据行 / ``[DONE]`` / 解析失败一律返回 ""。
    """
    try:
        text = bytes(chunk).decode(DEFAULT_ENCODING, errors="replace").strip()
    except Exception:
        return ""
    if not text.startswith("data:"):
        return ""
    body = text[5:].strip()
    if not body or body == "[DONE]":
        return ""
    try:
        obj = json.loads(body)
    except Exception:
        return ""
    try:
        choices = obj.get("choices") or []
        if not isinstance(choices, list) or not choices:
            return ""
        delta = choices[0].get("delta") or {}
        if not isinstance(delta, dict):
            return ""
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):     # 多模态分段 delta
            return "".join(p.get("text", "") for p in content
                           if isinstance(p, dict))
    except Exception:
        return ""
    return ""


def _relay_auto_ingest_enabled(engine: MemoryEngine) -> bool:
    """``llm.auto_ingest`` 开关（读不到时按开启处理，批 10）。"""
    try:
        return bool(getattr(engine.config.llm, "auto_ingest", True))
    except Exception:
        return True


def _relay_ingest_turn(
    engine: MemoryEngine,
    character: Optional[str],
    user_message: Optional[str],
    assistant_message: Optional[str],
    logger: logging.Logger,
    sync: bool = False,
    card: Optional[str] = None,
    messages: Optional[Sequence[Any]] = None,
) -> None:
    """把一轮对话交给 ``engine.ingest_turn_staged()``（批 10「边聊边记」）。

    * ``auto_ingest=false`` / 没识别到角色 / 这一轮没内容 -> 直接跳过
    * ``sync=True``  -> 就地执行（非流式路径，转发已经完成）
    * ``sync=False`` -> 丢进 daemon 线程异步执行（流式路径，不能拖慢响应）
    * ``card`` —— **V3 追加**：当前卡名，只用于分组 / 归属校验；
      流式路径以前漏传，V4 已补上
    * **V4**：这里不再直接写库 —— ``ingest_turn_staged`` 只把这一轮
      暂存到 ``conversation_meta``，等下一轮请求（user 消息变了 / 超时）
      才真正落库，所以 reroll 掉的版本永远不会进库
    * **V5**：``messages`` 是本次请求的**原始历史**（未注入记忆的那份）；
      落上一轮时先用它核对「用户实际留在界面上的那版 assistant」
      （历史里 user 后面跟着的那条），核对不到才退回暂存版
    * 内部已全部 try/except；这里再兜一层，**绝不影响主流程**
    """
    if not _relay_auto_ingest_enabled(engine):
        logger.debug("[中继] auto_ingest=false，跳过边聊边记")
        return
    if not character:
        logger.debug("[中继] 没识别到角色，跳过边聊边记")
        return
    user_text = _relay_fix_text(user_message).strip()
    assistant_text = _relay_fix_text(assistant_message).strip()
    if not user_text and not assistant_text:
        logger.debug("[中继] 这一轮没有内容，跳过边聊边记")
        return

    if _is_image_prompt_text(user_text) or _is_image_result_text(assistant_text):
        logger.info("[中继] 这一轮是生图提示词（不是剧情），整轮跳过"
                    "（不暂存/不落库/不抽取/不占暂存槽）：card=%s 角色=%s user=%d 字",
                    card, character, len(user_text))
        return

    def _run() -> None:
        try:
            # V4：改成「延迟一拍」——只暂存，不写库；上一轮该落库时才落库
            # V5：把本次请求的原始 messages 带下去，落库前用它核对
            #     「用户实际留在界面上的那版 assistant」
            engine.ingest_turn_staged(str(character), user_text, assistant_text,
                                      source=RELAY_INGEST_SOURCE,
                                      card=(_relay_fix_text(card).strip() or None),
                                      messages=messages)
        except Exception as ex:            # 兜底：回写失败也绝不冒泡
            logger.exception("[中继] 已回写：失败（已忽略）%s", ex)

    if sync:
        _run()
        return
    # [V6 阶段A] 异步路径改走 engine.ingest_turn_async()：
    #   daemon 线程 + self._ingest_serial_lock 串行化，
    #   并且受 llm.ingest_async 开关控制（false = 退回同步）
    try:
        engine.ingest_turn_async(
            str(character), user_text, assistant_text,
            source=RELAY_INGEST_SOURCE,
            card=(_relay_fix_text(card).strip() or None),
            messages=messages)
        logger.debug("[中继] 已回写：角色=%s 的回写丢到后台线程", character)
    except Exception as ex:
        logger.warning("[中继] 已回写：异步入口失败，退回同步：%s", ex)
        _run()


def _relay_resolve_card_speaker(
    engine: MemoryEngine,
    payload: Dict[str, Any],
    query: Optional[Dict[str, Any]],
    card_header: Optional[str],
    char_header: Optional[str],
    logger: logging.Logger,
) -> Dict[str, Any]:
    """**V3 中继主入口**：识别「当前卡 + 当前说话人」。

    直接转发 ``engine._detect_card_and_speaker()``（6 级优先级，含 LLM 兜底），
    返回值透传，另加一层兜底：整体异常时返回空结果，**绝不让识别失败影响转发**。
    """
    try:
        return engine._detect_card_and_speaker(
            payload.get("messages"), query,
            {RELAY_CARD_HEADER: card_header,
             RELAY_CHAR_HEADER: char_header})
    except Exception as ex:
        logger.warning("[中继] 卡/说话人识别异常（退化为不注入）：%s", ex)
    return {"card": None, "speaker": None, "characters": [],
            "source": DETECT_SOURCE_NONE}


def _relay_resolve_character(
    engine: MemoryEngine,
    payload: Dict[str, Any],
    query: Optional[Dict[str, Any]],
    char_header: Optional[str],
    logger: logging.Logger,
) -> Tuple[Optional[str], str]:
    """识别当前活跃角色（批 9：自动识别 + 自动注册，**不再 404**）。

    优先级（第一个成功就用）：

    1. ``?char=``        2. ``X-Character``
    3. ``messages`` 自动识别（assistant.name → content 扫描 → system prompt）
    4. ``config.llm.default_character``
    5. ``engine.resolve_active()``

    返回 ``(规范角色名, 来源)``；来源取值 ``query`` / ``header`` /
    ``assistant_name`` / ``content_scan`` / ``system_prompt`` / ``default`` /
    ``resolve_active``。全部失败返回 ``(None, "none")``，调用方退化为
    「不注入记忆、直接转发」。
    """
    detected: Optional[str] = None
    source = "none"
    try:
        detected = engine._detect_character_from_request(
            payload.get("messages"), query,
            {RELAY_CHAR_HEADER: char_header})
        source = getattr(engine, "last_char_source", "") or "none"
    except Exception as ex:
        logger.warning("[中继] 自动角色识别异常：%s", ex)

    if detected:
        row = _relay_get_or_create(engine, detected, logger)
        if row is not None:
            return str(row["name"]), source
        logger.warning("[中继] 识别到 %r（来源 %s）但无法注册，继续兜底",
                       detected, source)

    # 4) config.llm.default_character
    default_name = ""
    try:
        default_name = str(
            getattr(engine.config.llm, "default_character", "") or "").strip()
    except Exception as ex:
        logger.warning("[中继] 读取 default_character 失败：%s", ex)
    if default_name:
        row = _relay_get_or_create(engine, default_name, logger)
        if row is not None:
            return str(row["name"]), "default"

    # 5) 兜底：引擎的活跃角色检测（取第一个非 user 的活跃角色）
    try:
        info = engine.resolve_active() or {}
        for cid in list(info.get("active") or []):
            row = engine.char_mgr.get(cid)
            if row is not None and not bool(row.get("is_user")):
                return str(row["name"]), "resolve_active"
    except Exception as ex:
        logger.warning("[中继] resolve_active() 兜底失败：%s", ex)

    return None, "none"


def _relay_inject_block(messages: List[Any], block: str) -> List[Dict[str, Any]]:
    """把记忆上下文作为**独立 system message** 注入到 messages。

    [ABfix-B] 统一形态：记忆块恒为独立 system，插在**最后一条 user 之前**
    （近因效应）；角色卡那条 system 内容一字不动，也不再被拼接。

    * 有 user message → 插在最后一条 user 之前
    * 没有 user message（边缘情况）→ 追加到数组末尾，不报错
    """
    out: List[Any] = [dict(m) if isinstance(m, dict) else m for m in messages]

    last_user_idx: Optional[int] = None
    for i, m in enumerate(out):
        if not isinstance(m, dict):
            continue
        if str(m.get("role", "")).strip().lower() == "user":
            last_user_idx = i

    item = {"role": "system", "content": block}
    if last_user_idx is None:
        out.append(item)
    else:
        out.insert(last_user_idx, item)
    return [m for m in out if isinstance(m, dict)]


def _relay_meta_command(
    engine: MemoryEngine,
    messages: List[Any],
    user_text: str,
    character: str,
    log: logging.Logger,
) -> Optional[List[Any]]:
    """[元指令] 识别并剥离玩家给系统的指令。

    返回 ``None`` = 不是元指令（调用方保持原 messages 不动）；
    返回新 list = 已剥离（调用方用返回值替换**局部** messages）。

    **绝不修改传入的 messages**：它是 ``payload["messages"]``，后面
    ``_relay_ingest_turn`` 还要用它把原文落库（剥离不得影响已存原文）。
    """
    # [临时关闭] 用户很少用元指令，关掉以省每轮 1 次 LLM 调用 + 避免
    # flash 返回小说导致的 3 次重试浪费。恢复时删这两行。
    return None
    text = str(user_text or "").strip()
    if not text:
        return None
    det = engine.rel_mgr.detect_meta_command(text, character)
    if not isinstance(det, dict) or not det.get("is_meta"):
        return None
    try:
        conf = float(det.get("confidence") or 0.0)
    except Exception:
        conf = 0.0
    if conf != conf or conf < META_CMD_MIN_CONFIDENCE:
        log.info("[元指令] 命中但置信度 %.2f < %.2f，按普通对话处理",
                 conf, META_CMD_MIN_CONFIDENCE)
        return None
    changes = det.get("changes")
    if not isinstance(changes, list):
        changes = []
    n = engine.rel_mgr.apply_meta_command(changes)
    # [元指令→Event] 既成事实型（提议已被 prompt 判为 is_meta=false）落成 Event
    try:
        _meta_directive_event(engine, text, changes, character, log)
    except Exception as ex:
        log.warning("[元指令][Event] 失败（忽略）：%s", ex)
    log.info("[元指令] 识别到 %d 条变化，已从对话剥离（原文=%r）",
             n, text[:60])

    idx = None
    for i, m in enumerate(messages):
        if isinstance(m, dict) \
                and str(m.get("role", "")).strip().lower() == "user":
            idx = i
    out: List[Any] = [m for i, m in enumerate(messages) if i != idx]
    if not any(isinstance(m, dict)
               and str(m.get("role", "")).strip().lower() == "user"
               for m in out):
        out.append({"role": "user", "content": META_CMD_PLACEHOLDER})
    return out


def _meta_directive_event(
    engine: MemoryEngine,
    raw_text: str,
    changes: Any,
    character: str,
    log: logging.Logger,
) -> Optional[int]:
    """[元指令→Event] 把**既成事实型**元指令落成一条 Event（幂等）。

    * 去重用现有 ``events.dedup_hash``：``"directive_" + sha256(元指令原文)``
    * 已存在同 dedup_hash -> 直接复用，绝不重复建
    * 事件描述的是**客观发生的事**，不是"用户发出了指令"
    * 顺带给非用户方建一条 DIRECTIVE 长期记忆（走现有 add_memory，自带去重）
    """
    try:
        import hashlib as _hl
        mgr = getattr(engine, "event_mgr", None)
        if mgr is None:
            mgr = engine.mem_mgr._ensure_event_mgr()
        if mgr is None:
            return None
        reasons: List[str] = []
        fnames: List[str] = []
        for ch in (changes or []):
            if not isinstance(ch, dict):
                continue
            r = str(ch.get("reason") or "").strip()
            if r and r not in reasons:
                reasons.append(r)
            for k in ("from", "to"):
                nm = str(ch.get(k) or "").strip()
                if nm and nm not in fnames:
                    fnames.append(nm)
        obj = "；".join(reasons) if reasons else str(raw_text or "").strip()[:80]
        head = ""
        if len(fnames) >= 2:
            head = "%s与%s" % (fnames[0], fnames[1])
        elif fnames:
            head = fnames[0]
        summary = ("%s：%s" % (head, obj)) if head else obj
        summary = summary or str(raw_text or "").strip()[:80]
        dh = "directive_" + _hl.sha256(
            str(raw_text or "").encode("utf-8")).hexdigest()
        before = mgr.db.query_one(
            "SELECT event_id FROM events WHERE dedup_hash = ? LIMIT 1", (dh,))
        ev_id = mgr.create_event(
            summary=summary, event_type=DEFAULT_EVENT_TYPE,
            importance=0.7, emotional_intensity=0.6,
            occurred_at=now_iso(), is_factual=True, dedup=True,
            dedup_hash_override=dh)
        if ev_id is None:
            return None
        if before is not None and int(before["event_id"]) == int(ev_id):
            log.info("[元指令][Event] 命中去重，复用 event_id=%s（%s）", ev_id, summary[:40])
            return int(ev_id)
        log.info("[元指令][Event] 新建 event_id=%s summary=%s", ev_id, summary[:60])
        # 给非用户方写一条 DIRECTIVE 长期记忆（add_memory 自带 dedup）
        # 已核实：events -> memories 无自动路径，此处不是重复来源，是唯一来源
        try:
            usr = engine.char_mgr.get_user()
            uid = usr.get("character_id") if usr else None
            for nm in fnames:
                cid = engine.rel_mgr._resolve_meta_party(nm, uid)
                if cid is None or (uid is not None and int(cid) == int(uid)):
                    continue
                engine.mem_mgr.add_memory(
                    owner=cid, content=summary,
                    memory_type=MEM_TYPE_EPISODIC, importance=0.7,
                    source_event_id=int(ev_id),
                    source_type=MEM_SOURCE_DIRECTIVE)
        except Exception as ex:
            log.warning("[元指令][Event] 建 DIRECTIVE 记忆失败（忽略）：%s", ex)
        return int(ev_id)
    except Exception as ex:
        log.warning("[元指令][Event] 处理失败（忽略，不影响聊天）：%s", ex)
        return None


def _p0_init_relation(
    engine: MemoryEngine,
    character: str,
    sys_text: str,
    log: logging.Logger,
) -> None:
    """[P0] 首次遇到「角色 -> 用户」关系行时，从卡文本抽 7 维初始关系。

    * 卡文本为空的卡 -> 把本次 system message 落库到 cards.persona_text（只写一次）
    * 无卡文本 / LLM 未启用 / 抽取失败 -> 仍然标记 initialized=1，避免每轮重试
    * 本函数在 _relay_prepare 阶段调用，**无事务**，可安全调 LLM
    """
    char_row = engine.char_mgr.get(character)
    if char_row is None:
        return
    user_row = engine.char_mgr.get_user()
    if user_row is None:
        return
    cid = int(char_row["character_id"])
    uid = int(user_row["character_id"])
    if cid == uid:
        return
    if not engine.rel_mgr.needs_init(cid, uid):
        return
    # 确保关系行存在（默认值 + initialized=0）
    engine.rel_mgr.get_or_create(cid, uid)

    card_row = engine.card_mgr.card_of_character(cid)
    if card_row is not None:
        card_id = _to_int(card_row.get("card_id"))
        persona = str(card_row.get("persona_text") or "").strip()
    else:
        card_id = None
        persona = ""

    # 卡文本为空 -> 把本次 system message 落库（只写一次）
    if not persona and str(sys_text or "").strip():
        if card_id is None:
            _cname = str(card_row.get("name") if card_row is not None
                         else "") or character
            card_id = engine.card_mgr.get_or_create(_cname)
            if card_id is not None:
                engine.card_mgr.attach_character(card_id, cid)
        if card_id is not None:
            engine.card_mgr.set_persona_text(card_id, sys_text)
            persona = str(sys_text).strip()

    if not persona:
        log.warning("[P0] 无卡文本，跳过初始化（角色=%s）", character)
        engine.rel_mgr.mark_initialized(cid, uid)
        return

    ok = engine.rel_mgr.initialize_from_card(cid, uid, persona)
    if not ok:
        log.warning("[P0] 初始关系抽取未成功（角色=%s），保持默认值并标记已初始化",
                    character)
    engine.rel_mgr.mark_initialized(cid, uid)


def _relay_prepare(
    engine: MemoryEngine,
    payload: Dict[str, Any],
    query: Optional[Dict[str, Any]],
    char_header: Optional[str],
    log: logging.Logger,
    card_header: Optional[str] = None,
) -> Tuple[Optional[Tuple[int, bytes, str]], Dict[str, Any]]:
    """中继公共前置（批 8 抽出，非流式 / 流式共用；V3 改为"卡 + 说话人"）。

    1. ``messages`` 校验
    2. ``llm.enabled`` 校验
    3. ``inject_memory`` 为真时：``_relay_resolve_card_speaker()`` 识别
       **卡 + 说话人** -> 只注入 **说话人一个人** 的记忆
       （``build_context``）-> 包成一条 system message 注入
    4. 收集除 ``messages`` / ``temperature`` / ``max_tokens`` / ``stream``
       之外需要原样透传的字段（``model`` 为空时跳过，改用 config 里的）

    返回 ``(error, prep)``：``error`` 非 ``None`` 时是
    ``(状态码, 响应体字节, Content-Type)`` 三元组，调用方直接回给客户端；
    为 ``None`` 时 ``prep`` 含 ``messages`` / ``temperature`` / ``max_tokens`` /
    ``extra`` / ``character`` / ``card`` / ``characters`` / ``source`` /
    ``inject`` / ``stream``。
    """
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return _relay_error(400, "messages 缺失或为空", "invalid_request_error",
                            log), {}

    llm = engine.llm
    if not llm.enabled:
        return _relay_error(
            503, "LLM 未启用，请在 config.yaml 里配置 llm.enabled: true",
            "llm_unavailable", log), {}

    # ---- 识别入口诊断日志（INFO 级，**每次请求都打**，在识别开始之前）----
    # 排障用：一眼看出 Tavo 到底发了什么 system、每条消息带没带 name。
    # 非流式 / 流式共用本函数，所以 stream=true 也照样有。
    # [P0] sys_text 提到 try 外：识别输入日志 + 初始关系抽取都要用
    sys_text = ""
    try:
        for _m in messages:
            if isinstance(_m, dict) \
                    and str(_m.get("role", "")).strip().lower() == "system":
                sys_text = _relay_message_text(_m)
                break
        pairs = [(str(_m.get("role") or ""), str(_m.get("name") or ""))
                 for _m in messages if isinstance(_m, dict)]
        log.info("[中继] 识别输入: system=%r  roles=%s（共 %d 条消息）",
                 sys_text[:800], pairs[:6], len(pairs))
    except Exception as ex:
        log.warning("[中继] 识别输入日志打印失败：%s", ex)

    # === 诊断：dump 完整 payload（临时，只写文件不改逻辑）===
    try:
        import os as _os, json as _json, time as _time
        _d = _os.path.expanduser("~/relay_dump")
        _os.makedirs(_d, exist_ok=True)
        _f = _os.path.join(_d, _time.strftime("%Y%m%d_%H%M%S_full_")
                           + str(int(_time.time() * 1000) % 1000) + ".json")
        _slim = []
        _last_user_raw = ""
        for _m in messages or []:
            _role = (_m.get("role") if isinstance(_m, dict) else None)
            _c = (str(_m.get("content") or "") if isinstance(_m, dict) else "")
            _rlow = str(_role or "").strip().lower()
            if _rlow == "user":
                _last_user_raw = _c
            _item = {"role": _role,
                     "name": (_m.get("name") if isinstance(_m, dict) else None),
                     "len": len(_c)}
            if _rlow == "assistant":
                _item["head"] = _c[:200]
            else:
                _item["content_full"] = _c
            _slim.append(_item)
        _sysfull = next((str(_m.get("content") or "") for _m in (messages or [])
                         if isinstance(_m, dict)
                         and _m.get("role") == "system"), "")
        _obj = {"n_messages": len(messages or []),
                "query": str(query or ""),
                "char_header": str(char_header or ""),
                "card_header": str(card_header or ""),
                "system_len": len(_sysfull),
                "system_full": _sysfull,
                "user_before_strip": _last_user_raw,
                "messages": _slim}
        with open(_f, "w", encoding="utf-8") as _fp:
            _json.dump(_obj, _fp, ensure_ascii=False, indent=1)
    except Exception as _ex:
        log.warning("[诊断] payload dump 失败：%s", _ex)
    # === 诊断结束 ===

    inject = bool(getattr(engine.config.llm, "inject_memory", True))

    card: Optional[str] = None
    character: Optional[str] = None
    detect_chars: List[Any] = []
    source = DETECT_SOURCE_NONE
    out_messages: List[Any] = list(messages)
    if inject:
        # ---- V3：先认卡、再认说话人（含 LLM 兜底）----
        det = _relay_resolve_card_speaker(
            engine, payload, query, card_header, char_header, log)
        card = det.get("card") or None
        character = det.get("speaker") or None
        detect_chars = list(det.get("characters") or [])
        source = str(det.get("source") or DETECT_SOURCE_NONE)

        if not character:
            # 识别不到说话人时不再 404，退化为「不注入记忆，直接转发」
            log.info("[中继] 卡=%s 说话人=（未识别）（来源=%s），"
                     "不注入记忆，直接转发", card or "（无）", source)
        else:
            current_message = _relay_last_user_message(messages)
            # [P0] 首次遇到该「角色 -> 用户」关系行时，从卡文本抽取初始关系。
            #      必须在 build_context **之前**，首次对话就带上正确关系。
            try:
                _p0_init_relation(engine, character, sys_text, log)
            except Exception as ex:
                log.warning("[P0] 初始关系初始化异常（忽略）：%s", ex)
            # [元指令] 识别 + 剥离（只改转发的局部副本，不动 payload 原文）
            try:
                _stripped = _relay_meta_command(engine, messages,
                                                current_message,
                                                character, log)
            except Exception as ex:
                log.warning("[元指令] 处理异常（忽略）：%s", ex)
                _stripped = None
            if _stripped is not None:
                messages = _stripped
                current_message = _relay_last_user_message(messages)
            # [本轮在场] 从注入窗口最近 10 条收集在场角色名（算不出 = []，不加段落）
            try:
                _pn = engine._present_names_from_db(card)
            except Exception as ex:
                log.warning("[中继] 在场名单生成异常（忽略）：%s", ex)
                _pn = []
            # ★ 生图请求判定（2026-09-30）：模板被拼在卡规则之后，必须全文搜标记
            _lu_raw = ""
            for _m in (messages or []):
                if isinstance(_m, dict) and str(_m.get("role", "")).strip().lower() == "user":
                    _lu_raw = _relay_message_text(_m)
            _is_img_req = any(_mk in _lu_raw.lower() for _mk in IMG_REQ_INLINE_MARKERS)
            if _is_img_req:
                # ★ 生图请求 + card 空或来自活跃兜底 → 从 user 内容扫卡兜底
                if not card or source == DETECT_SOURCE_RESOLVE_ACTIVE:
                    _uc = engine.card_from_user_content(messages)
                    if _uc:
                        card = _uc
                _scene = _scene_context_for_image(engine, card)
                if _scene:
                    out_messages = _relay_inject_block(messages, _scene)
                    log.info("[中继] 生图请求：跳过角色注入，注入场景 %d 字 (card=%r)",
                             len(_scene), card)
                else:
                    out_messages = list(messages)
                    log.info("[中继] 生图请求：跳过角色注入（无场景可用，card=%r）", card)
            else:
                context = engine.build_context(character, current_message,
                                              present_names=_pn)
                block = (RELAY_MEMORY_INTRO % character) + "\n\n" + str(context or "")
                out_messages = _relay_inject_block(messages, block)
                log.info("[中继] 卡=%s 角色=%s（来源=%s）  current_message=%d 字，"
                         "注入上下文 %d 字",
                         card or "（无）", character, source,
                         len(current_message), len(block))
    else:
        log.info("[中继] 卡=（无）角色=（未识别）inject_memory=false，"
                 "纯转发（不注入记忆）")

    # 除 messages / temperature / max_tokens / stream 外，其余字段原样透传
    # （model 为空时用 config.yaml 里的 model）
    extra: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in ("messages", "temperature", "max_tokens", "stream"):
            continue
        if key == "model" and not str(value or "").strip():
            continue
        extra[key] = value

    prep: Dict[str, Any] = {
        "messages": out_messages,
        "temperature": _relay_opt_float(payload.get("temperature")),
        "max_tokens": _relay_opt_int(payload.get("max_tokens")),
        "extra": extra,
        "character": character,
        "card": card,
        "characters": detect_chars,
        "source": source,
        "inject": inject,
        "stream": bool(payload.get("stream")),
    }
    return None, prep


def relay_chat_completions(
    engine: MemoryEngine,
    payload: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
    char_header: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    card_header: Optional[str] = None,
) -> Tuple[int, bytes, str]:
    """中继主流程（**非流式**）：``(HTTP 状态码, 响应体字节, Content-Type)``。

    纯函数式接口，HTTP 层（``_Handler.do_POST``）只负责读 body / 发包。
    ``stream: true`` 的请求由 ``relay_chat_stream()`` 处理（批 8）；本函数
    即便收到 ``stream: true`` 也只按一次性 JSON 返回，不产出 SSE。
    """
    log = logger or _get_logger("relay")

    error, prep = _relay_prepare(engine, payload, query, char_header, log,
                                 card_header)
    if error is not None:
        return error

    llm = engine.llm
    data = llm.chat_raw(
        prep["messages"],
        temperature=prep["temperature"],
        max_tokens=prep["max_tokens"],
        extra=prep["extra"],
    )
    if data is None:
        return _relay_error(
            502, "上游 LLM 调用失败：%s" % (llm.last_error or "未知错误"),
            "upstream_error", log)

    raw = llm.last_raw
    body = (bytes(raw) if isinstance(raw, (bytes, bytearray)) and raw
            else _relay_json_bytes(data))
    log.info("[中继] 上游返回 %s，%d 字节", llm.last_status or 200, len(body))

    # 批 10：转发成功 -> 边聊边记
    # V3：把卡名一并带下去，供逐条 message 判归属
    # V6 阶段A：**改为异步**（sync=False）—— 回写与抽取丢进 daemon 线程，
    #          用户看到回复的时间不再被入库/LLM 抽取拖慢。
    #          关掉：config.yaml 里 llm.ingest_async: false（退回同步）
    _relay_ingest_turn(
        engine, prep.get("character"),
        _relay_last_user_message(payload.get("messages")),
        _relay_assistant_text(data), log, sync=False,
        card=prep.get("card"), messages=payload.get("messages"))

    return 200, body, "application/json; charset=utf-8"


def _relay_chain(first: bytes, rest: Iterator[bytes]) -> Iterator[bytes]:
    """把 peek 出来的第一块拼回流的开头（批 8 追加）。"""
    yield first
    for chunk in rest:
        yield chunk


def relay_chat_stream(
    engine: MemoryEngine,
    payload: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
    char_header: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    card_header: Optional[str] = None,
) -> Tuple[Optional[Tuple[int, bytes, str]], Optional[Iterator[bytes]],
           Dict[str, Any]]:
    """流式中继（``stream: true``）：返回 ``(error, chunks, meta)``。

    * 前置校验 + 记忆注入与 ``relay_chat_completions()`` 完全一致（同一个
      ``_relay_prepare()``），所以照样会调 ``build_context()``
    * **先把上游第一块 peek 出来**再返回：上游连不上 / 非 2xx 时 ``error``
      是标准错误三元组，此时一个字节都还没写给客户端，可以正常回 JSON 502
    * ``error`` 为 ``None`` 时，``chunks`` 是可直接转发的上游 SSE 字节流
      （第一块已放回，不会丢；用完记得 ``close()``）
    * ``meta`` 供批 10「边聊边记」用：``character``（识别到的说话人）、
      ``card``（V3 追加：识别到的卡）与 ``user_message``（这一轮的 user 文本）
    """
    log = logger or _get_logger("relay")

    error, prep = _relay_prepare(engine, payload, query, char_header, log,
                                 card_header)
    if error is not None:
        return error, None, {}

    meta: Dict[str, Any] = {
        "character": prep.get("character"),
        "card": prep.get("card"),
        "user_message": _relay_last_user_message(payload.get("messages")),
        # V5：原始历史（未注入记忆的那份），落上一轮时用它核对用户留下的版本
        "messages": payload.get("messages"),
    }

    llm = engine.llm
    gen = llm.chat_stream(
        prep["messages"],
        temperature=prep["temperature"],
        max_tokens=prep["max_tokens"],
        extra=prep["extra"],
    )
    first = next(gen, None)
    if first is None:
        return _relay_error(
            502, "上游 LLM 流式调用失败：%s" % (llm.last_error or "未知错误"),
            "upstream_error", log), None, {}

    log.info("[中继] 流式开始：卡=%s 角色=%s，上游 %s，流式转发中",
             prep.get("card") or "（无）", prep["character"],
             llm.last_status or 200)
    return None, _relay_chain(first, gen), meta


# ==============================================================================
# 26. CLI —— argparse 子命令 + 输出
# ==============================================================================

# 批 5 追加：CLI 层需要的标准库模块（就地导入，不改动文件头）
import argparse  # noqa: E402

#: 全部子命令名（用于 ``python memory_full.py chat.jsonl`` 的快捷展开）
SUBCOMMANDS: Tuple[str, ...] = (
    "init", "import", "characters", "detect-active", "memories",
    "relationships", "state", "context", "beliefs", "visibility",
    "set-role", "set-profile", "add-memory", "add-belief", "add-knowledge",
    "add-commitment", "add-secret", "add-visibility",
    "consolidate", "extract", "decay", "stats", "serve",
    "list-cards", "attach-card", "migrate-card", "detach-card",
    # [V6 阶段D] 安全聚合合并：不加进来会被快捷展开当成 `import merge-memories`
    "merge-memories",
    # [relations-7] 手工关系层级设定（同理，不加会被展开成 import）
    "set-relation-level",
)

#: 需要跟一个值的全局选项（快捷展开时要跳过它们的值）
_GLOBAL_VALUE_FLAGS: Tuple[str, ...] = ("--db", "--config", "--log-dir")


# ══════════════════════════════════════════════════════════════════════
# 【20】CLI 层
# ══════════════════════════════════════════════════════════════════════

def _force_utf8_stdout() -> None:
    """把 stdout / stderr 切成 UTF-8，避免 Windows 控制台打不出中文。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding=DEFAULT_ENCODING, errors="replace")
        except Exception:
            pass


def _out(text: Any = "") -> None:
    """安全打印（控制台编码不支持时降级替换，绝不因打印崩掉）。"""
    msg = "" if text is None else str(text)
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or DEFAULT_ENCODING
        try:
            print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))
        except Exception:
            pass
    except Exception:
        pass


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    """极简等宽表格（按显示宽度粗略对齐，中文按 2 列算）。"""
    def width(s: Any) -> int:
        return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(s))

    cells = [[str(c) for c in r] for r in rows]
    cols = [list(c) for c in zip(*([list(headers)] + cells))] if (rows or headers) else []
    if not cols:
        return
    widths = [max(width(c) for c in col) for col in cols]
    def line(items: Sequence[Any]) -> str:
        parts = []
        for item, w in zip(items, widths):
            pad = " " * max(1, w - width(item) + 2)
            parts.append("%s%s" % (item, pad))
        return "".join(parts).rstrip()
    _out(line(headers))
    _out("".join("-" * (w + 2) for w in widths))
    for row in cells:
        _out(line(row))


def _kv(title: str, pairs: Sequence[Sequence[Any]]) -> None:
    """打印一组 ``键 : 值``。"""
    _out(title)
    for k, v in pairs:
        _out("  %-14s %s" % ("%s:" % k, v))


def _open_engine(args: Any) -> MemoryEngine:
    """按 CLI 参数打开引擎（--config / --db / --debug 生效）。"""
    cfg = load_config(getattr(args, "config", None))
    if getattr(args, "db", None):
        cfg.db_path = str(args.db)
    if getattr(args, "debug", False):
        cfg.debug = True
    engine = MemoryEngine(db_path=cfg.db_path, config=cfg)
    try:
        setattr(args, "engine_obj", engine)
    except Exception:
        pass
    return engine


def _normalize_shortcut(argv: Sequence[str]) -> List[str]:
    """``python memory_full.py chat.jsonl`` -> ``... import chat.jsonl``。

    只在"第一个非选项 token 确实不是子命令"时才改写；已经带子命令、
    或者只有 ``--help`` 之类的调用原样返回。
    """
    known = set(SUBCOMMANDS) | {"-h", "--help", "--version", "-V"}
    i = 0
    n = len(argv)
    while i < n:
        tok = str(argv[i])
        if tok.startswith("--") and "=" in tok:
            i += 1
            continue
        if tok in _GLOBAL_VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if tok in known:
            return list(argv)
        return list(argv[:i]) + ["import"] + list(argv[i:])
    return list(argv)


# ==============================================================================
# 26.1 各子命令实现（cmd_*）
# ==============================================================================


def cmd_init(args: Any) -> int:
    """``init`` —— 建库建表，打印统计。"""
    engine = _open_engine(args)
    _out("数据库已就绪：%s" % engine.config.db_path)
    _out("表：%s" % ", ".join(sorted(engine.db.table_names())))
    st = engine.summary_stats()
    _kv("当前统计", [
        ("角色", st["characters"]), ("消息", st["messages"]),
        ("未处理", st["unprocessed"]), ("事件", st["events"]),
        ("可见性", st["event_visibility"]), ("记忆", st["memories"]),
        ("信念", st["beliefs"]), ("知识", st["knowledge"]),
        ("关系", st["relationships"]), ("承诺", st["commitments"]),
        ("秘密", st["secrets"]), ("LLM", "启用" if st["llm_enabled"] else "关闭"),
    ])
    return 0


def cmd_import(args: Any) -> int:
    """``import FILE [--mode]`` —— 导入聊天记录并增量抽取。"""
    engine = _open_engine(args)
    path = Path(args.file)
    if not path.is_file():
        _out("文件不存在：%s" % path)
        return 1
    report = engine.import_jsonl(
        path, mode=args.mode, process=not args.no_process, limit=args.limit)
    st = report.get("import") or {}
    if st.get("errors"):
        for e in st["errors"][:10]:
            _out("  警告：%s" % e)
    _kv("导入结果", [
        ("文件", st.get("path", str(path))),
        ("总行数", st.get("total_lines", 0)),
        ("可解析", st.get("parsed", 0)),
        ("新增消息", st.get("imported", 0)),
        ("重复跳过", st.get("skipped", 0)),
        ("空消息跳过", st.get("empty_skipped", 0)),
        ("坏行", st.get("bad_lines", 0)),
        ("涉及角色", "、".join(st.get("characters") or []) or "（无）"),
    ])
    ex = report.get("extraction") or {}
    _kv("抽取结果（模式 %s）" % ex.get("mode", args.mode or DEFAULT_MODE), [
        ("处理消息", ex.get("processed", 0)),
        ("批次数", ex.get("batches", 0)),
        ("事件", ex.get("events", 0)),
        ("可见性", ex.get("visibility", 0)),
        ("记忆", ex.get("memories", 0)),
        ("信念", ex.get("beliefs", 0)),
        ("知识", ex.get("knowledge", 0)),
        ("承诺", ex.get("commitments", 0)),
        ("秘密", ex.get("secrets", 0)),
        ("关系变化", ex.get("relationship_changes", 0)),
        ("状态变化", ex.get("state_changes", 0)),
        ("异常", ex.get("errors", 0)),
    ])
    return 0


def cmd_characters(args: Any) -> int:
    """``characters`` —— 角色列表。"""
    engine = _open_engine(args)
    rows = engine.list_characters(with_counts=True)
    if not rows:
        _out("还没有角色。先导入聊天记录：python %s chat.jsonl" % APP_NAME)
        return 0
    _table(["ID", "名字", "角色类型", "活跃", "消息", "记忆", "信念", "知识"],
           [[r.get("character_id"), r.get("name"), r.get("role_type"),
             "是" if r.get("active") else "否", r.get("message_count") or 0,
             r.get("memory_count") or 0, r.get("belief_count") or 0,
             r.get("knowledge_count") or 0] for r in rows])
    _out("共 %d 个角色" % len(rows))
    return 0


def cmd_detect_active(args: Any) -> int:
    """``detect-active`` —— 刷新活跃角色 + 核心角色候选。"""
    engine = _open_engine(args)
    res = engine.resolve_active(
        window_messages=args.window, window_hours=args.hours)
    names = []
    for cid in res["active"]:
        row = engine.char_mgr.get(cid)
        if row:
            names.append("%s(%s)" % (row.get("name"), cid))
    _out("活跃角色 %d 个：%s" % (len(res["active"]), "、".join(names) or "（无）"))
    if res["promoted"]:
        pnames = []
        for cid in res["promoted"]:
            row = engine.char_mgr.get(cid)
            if row:
                pnames.append("%s(%s)" % (row.get("name"), cid))
        _out("提升为核心角色 %d 个：%s" % (len(res["promoted"]), "、".join(pnames)))
    return 0


def cmd_memories(args: Any) -> int:
    """``memories NAME [--limit N] [--query Q] [--debug]`` —— 看某角色的记忆。"""
    engine = _open_engine(args)
    row = engine.char_mgr.get(args.name)
    if row is None:
        _out("没找到角色：%s" % args.name)
        return 1
    cid = int(row["character_id"])
    if args.query:
        mems = engine.mem_mgr.retrieve(
            cid, query=args.query, limit=args.limit, debug=args.debug)
    else:
        mems = engine.mem_mgr.list_for(cid, limit=args.limit)
    _out("角色 %s（id=%s）记忆 %d 条%s"
         % (row.get("name"), cid, len(mems),
            "，关键词「%s」" % args.query if args.query else ""))
    for m in mems:
        head = "[%s] #%s %s 重要%.2f 强度%.2f" % (
            m.get("memory_type"), m.get("memory_id"), m.get("status"),
            _clamp(m.get("importance"), 0.0, 1.0, DEFAULT_IMPORTANCE),
            float(m.get("recall_strength") or 0.0))
        if m.get("_score") is not None:
            head += " 分%.3f" % float(m["_score"])
        _out(head)
        _out("    %s" % str(m.get("content") or "").replace("\n", " "))
        if args.debug and m.get("_debug"):
            _out("    评分明细：%s" % json.dumps(
                m["_debug"], ensure_ascii=False, default=str))
        tags = [str(t) for t in _as_list(m.get("tags"))]
        if tags:
            _out("    tags=%s" % " ".join(tags))
    return 0


def cmd_relationships(args: Any) -> int:
    """``relationships`` —— 全库单向关系。"""
    engine = _open_engine(args)
    rows = engine.rel_mgr.all()
    if not rows:
        _out("还没有关系记录")
        return 0
    _table(["方向", "信任", "好感", "怨恨", "熟悉", "尊重", "恐惧", "依赖"],
           [["%s → %s" % (r.get("from_name"), r.get("to_name")),
             "%.2f" % _clamp(r.get("trust"), 0, 1, 0.5),
             "%.2f" % _clamp(r.get("affection"), 0, 1, 0.5),
             "%.2f" % _clamp(r.get("resentment"), 0, 1, 0.0),
             "%.2f" % _clamp(r.get("familiarity"), 0, 1, 0.5),
             "%.2f" % _clamp(r.get("respect"), 0, 1, 0.5),
             "%.2f" % _clamp(r.get("fear"), 0, 1, 0.0),
             "%.2f" % _clamp(r.get("dependency"), 0, 1, 0.0)]
            for r in rows])
    for r in rows:
        if r.get("state_summary"):
            _out("  %s → %s：%s" % (r.get("from_name"), r.get("to_name"),
                                    r["state_summary"]))
    return 0


def cmd_set_relation_level(args: Any) -> int:
    """``set-relation-level`` —— 手工把某维度设到指定层级。

    走 ``set_value``（绕过 |delta|>0.5 上限，专为 Python / CLI 显式设定设计），
    用于"出轨 / 救命 / 关系永久破裂"这类 catastrophic 事件的人工触发。
    """
    engine = _open_engine(args)
    try:
        level = str(getattr(args, "level", "") or "").strip().lower()
        value = META_LEVEL_VALUES.get(level)
        if value is None:
            _out("未知层级 %r；可选：%s"
                 % (level, "、".join(sorted(META_LEVEL_VALUES))))
            return 2
        dim = str(getattr(args, "dim", "") or "").strip().lower()
        if dim not in ALLOWED_REL_FIELDS:
            _out("未知维度 %r；可选：%s" % (dim, "、".join(ALLOWED_REL_FIELDS)))
            return 2
        usr = engine.char_mgr.get_user()
        uid = usr.get("character_id") if usr else None
        from_c = engine.rel_mgr._resolve_meta_party(
            getattr(args, "from_name", None), uid)
        to_c = engine.rel_mgr._resolve_meta_party(
            getattr(args, "to_name", None), uid)
        if from_c is None or to_c is None:
            _out("无法解析角色：%r -> %r"
                 % (getattr(args, "from_name", None),
                    getattr(args, "to_name", None)))
            return 1
        reason = str(getattr(args, "reason", "") or "")
        ok = engine.rel_mgr.set_value(
            from_c, to_c, dim, value, reason=reason,
            source_event_id=getattr(args, "event_id", None))
        if not ok:
            _out("设定失败（字段非法或关系行创建失败）")
            return 1
        try:
            engine.rel_mgr.apply_hate_floor(from_c, to_c)
        except Exception:
            pass
        _out("[关系] CLI 设定 %s → %s %s 到 %.2f（%s）%s"
             % (getattr(args, "from_name", None),
                getattr(args, "to_name", None), dim, value, level,
                ("，原因：%s" % reason) if reason else ""))
        return 0
    finally:
        try:
            engine.close()
        except Exception:
            pass


def cmd_state(args: Any) -> int:
    """``state NAME`` —— 某角色当前状态 + 最近变更。"""
    engine = _open_engine(args)
    row = engine.char_mgr.get(args.name)
    if row is None:
        _out("没找到角色：%s" % args.name)
        return 1
    cid = int(row["character_id"])
    st = engine.state_mgr.get(cid)
    _out("角色 %s（id=%s）" % (row.get("name"), cid))
    _out("  %s" % engine.state_mgr.describe(cid))
    if st:
        for key in ("emotion", "mood", "anger", "fear", "stress",
                    "current_goal", "current_location", "physical_state",
                    "mental_context", "unresolved_conflicts", "summary"):
            if st.get(key) not in (None, ""):
                _out("    %-20s %s" % (key, st[key]))
    hist = engine.state_mgr.history(cid, limit=10)
    if hist:
        _out("  最近变更：")
        for h in hist:
            _out("    %s  %s: %s -> %s  %s"
                 % (str(h.get("changed_at") or "")[:19], h.get("field"),
                    h.get("old_value"), h.get("new_value"),
                    h.get("reason") or ""))
    return 0


def cmd_context(args: Any) -> int:
    """``context NAME [MSG] [--debug]`` —— 生成角色上下文。"""
    engine = _open_engine(args)
    row = engine.char_mgr.get(args.name)
    if row is None:
        _out("没找到角色：%s" % args.name)
        return 1
    text = engine.build_context(
        int(row["character_id"]), current_message=args.message or "",
        debug=args.debug)
    _out(text)
    _out("")
    _out("（共 %d 字）" % len(text))
    return 0


def cmd_beliefs(args: Any) -> int:
    """``beliefs NAME [--kind KIND]`` —— 某角色的信念。"""
    engine = _open_engine(args)
    row = engine.char_mgr.get(args.name)
    if row is None:
        _out("没找到角色：%s" % args.name)
        return 1
    cid = int(row["character_id"])
    kind = (args.kind or "").strip().upper() or None
    bs = engine.belief_mgr.list_for(cid, kind=kind, status=None)
    _out("角色 %s 的信念 %d 条%s"
         % (row.get("name"), len(bs),
            "（kind=%s）" % kind if kind else ""))
    for b in bs:
        ref = "（%s）" % b["subject_ref"] if b.get("subject_ref") else ""
        _out("  [%s/%s/%s] %.2f  %s%s"
             % (b.get("kind"), b.get("subject_kind"), b.get("status"),
                _clamp(b.get("confidence"), 0, 1, DEFAULT_BELIEF_CONFIDENCE),
                b.get("statement"), ref))
    return 0


def cmd_visibility(args: Any) -> int:
    """``visibility NAME [--event-id ID]`` —— 某角色知道 / 怀疑 / 听说的事件。"""
    engine = _open_engine(args)
    row = engine.char_mgr.get(args.name)
    if row is None:
        _out("没找到角色：%s" % args.name)
        return 1
    cid = int(row["character_id"])
    if args.event_id is not None:
        one = engine.vis_mgr.get_visibility(args.event_id, cid)
        rows = [one] if one else []
    else:
        rows = engine.vis_mgr.list_for_character(cid)
    _out("角色 %s 的可见性记录 %d 条" % (row.get("name"), len(rows)))
    for v in rows:
        _out("  [%s] 事件#%s present=%s role=%s conf=%.2f src=%s"
             % (v.get("state"), v.get("event_id"),
                "1" if v.get("present") else "0",
                v.get("role_in_event"), _clamp(v.get("confidence"), 0, 1, 0.7),
                v.get("source")))
        if v.get("partial_content"):
            _out("      只知道：%s" % v["partial_content"])
        if v.get("event_summary"):
            _out("      事件：%s" % v["event_summary"])
        mids = [str(x) for x in _as_list(v.get("source_message_ids"))]
        if mids:
            _out("      来源消息：%s" % "、".join(mids[:5]))
    return 0


def cmd_set_role(args: Any) -> int:
    """``set-role NAME ROLE`` —— 设置角色类型（新增角色不需要改代码）。"""
    engine = _open_engine(args)
    ok = engine.char_mgr.get_or_create(args.name, role_type=args.role)
    if ok is None:
        _out("设置失败：%s" % args.name)
        return 1
    if not engine.set_role(args.name, args.role):
        _out("设置失败（角色类型非法？）：%s / %s" % (args.name, args.role))
        return 1
    _out("已把 %s 设为 %s" % (args.name, args.role))
    return 0


def cmd_set_profile(args: Any) -> int:
    """``set-profile NAME --json '{...}'`` —— 设置角色静态档案。"""
    engine = _open_engine(args)
    try:
        profile = json.loads(args.json)
    except Exception as ex:
        _out("--json 不是合法 JSON：%s" % ex)
        return 1
    if not isinstance(profile, dict):
        _out("--json 必须是对象（{...}）")
        return 1
    if engine.char_mgr.get(args.name) is None:
        engine.char_mgr.get_or_create(args.name)
    if not engine.char_mgr.set_static_profile(args.name, profile):
        _out("写入失败：%s" % args.name)
        return 1
    _out("已更新 %s 的档案：%s" % (args.name,
                                 json.dumps(profile, ensure_ascii=False)))
    return 0


def cmd_add_memory(args: Any) -> int:
    """``add-memory NAME CONTENT [--type] [--importance] [--emotion]``"""
    engine = _open_engine(args)
    if engine.char_mgr.get(args.name) is None:
        engine.char_mgr.get_or_create(args.name)
    mid = engine.mem_mgr.add_memory(
        owner=args.name, content=args.content, memory_type=args.memory_type,
        importance=args.importance, emotional_intensity=args.emotion,
        source_type=args.source_type,
        tags=args.tag or None)
    if mid is None:
        _out("写入被拒绝（校验未通过），详见日志")
        return 1
    _out("已写入记忆 #%s（owner=%s type=%s）"
         % (mid, args.name, args.memory_type))
    return 0


def cmd_add_belief(args: Any) -> int:
    """``add-belief NAME --kind KIND --subject-ref REF --statement TEXT``"""
    engine = _open_engine(args)
    if engine.char_mgr.get(args.name) is None:
        engine.char_mgr.get_or_create(args.name)
    kind = args.kind.strip().upper()
    gen = GENERATED_BY_RULE if kind == BELIEF_FACT else GENERATED_BY_LLM
    bid = engine.belief_mgr.add_belief(
        owner=args.name, kind=kind, subject_kind=args.subject_kind,
        statement=args.statement, subject_ref=args.subject_ref,
        confidence=args.confidence, generated_by=gen,
        source="cli")
    if bid is None:
        _out("写入被拒绝（kind / subject_kind 非法？），详见日志")
        return 1
    _out("已写入信念 #%s（%s，generated_by=%s）" % (bid, kind, gen))
    return 0


def cmd_add_knowledge(args: Any) -> int:
    """``add-knowledge NAME SUBJECT [--status] [--confidence]``"""
    engine = _open_engine(args)
    if engine.char_mgr.get(args.name) is None:
        engine.char_mgr.get_or_create(args.name)
    kid = engine.know_mgr.set_knowledge(
        owner=args.name, subject=args.subject, status=args.status,
        confidence=args.confidence, source="cli")
    if kid is None:
        _out("写入被拒绝（status 非法？），详见日志")
        return 1
    _out("已写入知识 #%s（%s：%s）" % (kid, args.status, args.subject))
    return 0


def cmd_add_commitment(args: Any) -> int:
    """``add-commitment NAME PROMISEE CONTENT [--deadline]``"""
    engine = _open_engine(args)
    for nm in (args.name, args.promisee):
        if nm and engine.char_mgr.get(nm) is None:
            engine.char_mgr.get_or_create(nm)
    cid = engine.commit_mgr.add(
        promiser=args.name, promisee=args.promisee, content=args.content,
        deadline=args.deadline, notes="cli")
    if cid is None:
        _out("写入被拒绝，详见日志")
        return 1
    _out("已写入承诺 #%s：%s 答应 %s —— %s"
         % (cid, args.name, args.promisee or "（未指定对象）", args.content))
    return 0


def cmd_add_secret(args: Any) -> int:
    """``add-secret NAME CONTENT [--subject]``"""
    engine = _open_engine(args)
    if engine.char_mgr.get(args.name) is None:
        engine.char_mgr.get_or_create(args.name)
    sid = engine.secret_mgr.add(
        owner=args.name, content=args.content,
        subject=args.subject or "")
    if sid is None:
        _out("写入被拒绝，详见日志")
        return 1
    _out("已写入秘密 #%s（owner=%s）" % (sid, args.name))
    return 0


def cmd_add_visibility(args: Any) -> int:
    """``add-visibility EVENT_ID NAME --state STATE [...]``

    CLI 是**人工显式**写入，因此默认 ``force=True``（SPEC「CLI 手工调用
    add-visibility 时，默认允许 force=True」）。
    """
    engine = _open_engine(args)
    if engine.char_mgr.get(args.name) is None:
        engine.char_mgr.get_or_create(args.name)
    cid = engine.char_mgr.resolve_id(args.name)
    if cid is None:
        _out("没找到角色：%s" % args.name)
        return 1
    vis_id = engine.vis_mgr.set_visibility(
        event_id=args.event_id, character_id=cid, state=args.state,
        partial_content=args.partial, source=args.source,
        source_message_id=args.source_message_id,
        present=not args.not_present, force=True)
    if vis_id is None:
        _out("写入被拒绝（降级 / 缺 partial_content / 事件或角色不存在？），详见日志")
        return 1
    _out("已写入可见性 #%s：事件 %s / %s = %s"
         % (vis_id, args.event_id, args.name, args.state))
    return 0


def cmd_consolidate(args: Any) -> int:
    """``consolidate [--mode fast|normal|deep]`` —— 记忆压缩（原始永不删除）。

    SPEC：``fast`` -> ``consolidated_mode='raw'``（拼接 + 300 字截断）；
    ``normal`` / ``deep`` -> ``consolidated_mode='llm'``（失败回退 raw）；
    ``deep`` 额外允许"二次整合"。
    """
    engine = _open_engine(args)
    cli_mode = str(args.mode or MODE_FAST).strip().lower()
    if cli_mode not in VALID_MODES:
        _out("未知模式 %r，回落 %s" % (args.mode, MODE_FAST))
        cli_mode = MODE_FAST
    res = engine.consolidate_all(
        mode=cli_mode, threshold=args.threshold,
        allow_nested=(cli_mode == MODE_DEEP),
        # CLI 是人手动敲的命令 -> 手动轮（不跳过 tier1）；未来自动/定时调用
        # consolidate 时必须保持默认 manual_trigger=False（保护 tier1）。
        manual_trigger=True)
    _out("压缩模式 %s（落库 consolidated_mode=%s，二次整合=%s），阈值 %s："
         "新增摘要 %d 条，逾期承诺 %d 条"
         % (cli_mode, res["mode"], "开" if res["nested"] else "关",
            res["threshold"], res["consolidated"], res["overdue"]))
    return 0


def cmd_extract(args: Any) -> int:
    """``extract [--mode]`` —— 只对未处理消息做增量抽取。"""
    engine = _open_engine(args)
    before = engine.importer.unprocessed_count()
    if before == 0:
        _out("没有待处理消息（processed = 0 的消息为 0）")
        return 0
    res = engine.process_pending(mode=args.mode, limit=args.limit)
    _kv("抽取结果（模式 %s）" % res["mode"], [
        ("待处理（前）", before),
        ("处理消息", res["processed"]),
        ("批次数", res["batches"]),
        ("空结果批", res["empty"]),
        ("事件", res["events"]),
        ("可见性", res["visibility"]),
        ("记忆", res["memories"]),
        ("信念", res["beliefs"]),
        ("知识", res["knowledge"]),
        ("承诺", res["commitments"]),
        ("秘密", res["secrets"]),
        ("关系变化", res["relationship_changes"]),
        ("状态变化", res["state_changes"]),
        ("剩余未处理", engine.importer.unprocessed_count()),
        ("异常", res["errors"]),
    ])
    for s in (res.get("skipped") or [])[:15]:
        _out("  拒绝：%s" % s)
    return 0


def cmd_decay(args: Any) -> int:
    """``decay [--rate F]`` —— 记忆衰减（不删除任何记忆）。"""
    engine = _open_engine(args)
    n = engine.apply_decay(rate=args.rate)
    _out("衰减完成：影响 %d 条记忆（记忆永不物理删除，只降 recall_strength）" % n)
    return 0


def cmd_merge_memories(args: Any) -> int:
    """``merge-memories`` —— 手动跑一轮安全聚合合并（[V6 阶段D]）。

    粗筛（owner -> tier -> 30 天窗口 + difflib）-> LLM 终审 ->
    短事务写入。旧记忆只把 ``status`` 改成 weakened（ID 不变、绝不删除）；
    LLM 拒绝 / 报错 / 不确定的组一律放弃，**不做拼接兜底**。
    """
    engine = _open_engine(args)
    res = engine.merge_similar_memories(manual_trigger=True)
    _kv("安全聚合合并（[V6 阶段D]）：", [
        ("扫描", res.get("scanned", 0)),
        ("候选组", res.get("groups", 0)),
        ("合并成功", res.get("merged", 0)),
        ("新记忆 id", res.get("new_ids") or "（无）"),
        ("跳过", res.get("skipped", 0)),
        ("用时(ms)", res.get("duration_ms", 0)),
    ])
    if res.get("error"):
        _out("本轮异常（已忽略）：%s" % res["error"])
    _out("旧记忆只把 status 改成 %s（ID 不变、不删除）；"
         "未通过 LLM 终审的组一律放弃，绝不拼接兜底。" % MERGE_OLD_STATUS)
    return 0


def cmd_stats(args: Any) -> int:
    """``stats`` —— 全库统计。"""
    engine = _open_engine(args)
    st = engine.summary_stats()
    _kv("memory_full %s（schema v%s）" % (st["version"], st["schema_version"]), [
        ("数据库", st["db_path"]),
        ("角色", st["characters"]),
        ("消息", st["messages"]),
        ("未处理", st["unprocessed"]),
        ("事件", st["events"]),
        ("事件链", st["event_chains"]),
        ("可见性", st["event_visibility"]),
        ("记忆", st["memories"]),
        ("知识", st["knowledge"]),
        ("信念", st["beliefs"]),
        ("关系", st["relationships"]),
        ("角色状态", st["character_states"]),
        ("承诺", st["commitments"]),
        ("秘密", st["secrets"]),
        ("记忆关联", st["associations"]),
        ("冲突记录", st["memory_conflicts"]),
        ("LLM", "启用（%s）" % engine.llm.describe()["model"]
         if st["llm_enabled"] else "关闭"),
    ])
    for title, key, label in (
            ("记忆状态分布", "memory_status", "status"),
            ("可见性分布", "visibility_by_state", "state"),
            ("信念分布", "beliefs_by_kind", "kind")):
        rows = st.get(key) or []
        if rows:
            _kv(title, [(r.get(label, "?"), r.get("n", 0)) for r in rows])
    if st["unprocessed"]:
        _out("提示：还有 %d 条消息未抽取，跑 `python %s extract`"
             % (st["unprocessed"], APP_NAME))
    return 0


def cmd_serve(args: Any) -> int:
    """``serve [--host] [--port]`` —— 启动手机可用的记忆控制台。"""
    engine = _open_engine(args)
    host = args.host or engine.config.host
    port = args.port or engine.config.port
    server = WebServer(engine, host=host, port=port)
    # ---- [V6 阶段D] 挂上自动聚合合并调度器（每 merge_interval_min 分钟）----
    # 只有 config.memory.auto_merge 与 merge_enabled 都为 true 才挂；
    # Timer 是 daemon，Ctrl+C 不会被它拖住（不用改 serve_forever/close）。
    try:
        if (bool(getattr(engine.config.memory, "auto_merge", True))
                and bool(getattr(engine.config.memory, "merge_enabled", True))):
            engine.start_merge_scheduler()
        else:
            engine.logger.info(
                "[合并] auto_merge/merge_enabled 有 false，不挂自动调度器")
    except Exception as ex:
        engine.logger.warning("[合并] 调度器启动失败（已忽略）：%s", ex)
    return server.serve_forever()


# ==============================================================================
# 26.2 参数解析
# ==============================================================================


# ==============================================================================
# 26.2 V3 追加：卡片层 CLI（list-cards / attach-card / migrate-card / detach-card）
# ==============================================================================


def cmd_list_cards(args: Any) -> int:
    """``list-cards`` —— 列出所有卡 + 卡下角色数 + 记忆数，附散装角色。"""
    engine = _open_engine(args)
    cards = engine.card_mgr.list_all()
    if cards:
        _table(["ID", "卡名", "来源", "角色", "记忆", "最近活跃"],
               [[c.get("card_id"), c.get("name"), c.get("source"),
                 c.get("character_count") or 0, c.get("memory_count") or 0,
                 str(c.get("last_seen") or "")[:19]] for c in cards])
    else:
        _out("还没有卡片。中继带一次卡名（?card= / X-Card）就会自动建卡。")
    _out("共 %d 张卡" % len(cards))

    loose = engine.card_mgr.loose_characters()
    if loose:
        _out("")
        _out("散装角色（card_id 为空，%d 个）：" % len(loose))
        _table(["ID", "名字", "角色类型", "消息", "记忆"],
               [[r.get("character_id"), r.get("name"), r.get("role_type"),
                 r.get("message_count") or 0, r.get("memory_count") or 0]
                for r in loose])
        _out("把它们归卡：python %s attach-card 角色名 --card 卡名" % APP_NAME)
    return 0


def cmd_attach_card(args: Any) -> int:
    """``attach-card CHAR --card CARD`` —— 把已存在的角色挂到卡上。"""
    engine = _open_engine(args)
    card_name = str(args.card or "").strip()
    char_name = str(args.name or "").strip()
    if not card_name or not char_name:
        _out("用法：python %s attach-card 角色名 --card 卡名" % APP_NAME)
        return 2
    row = engine.char_mgr.get(char_name)
    if row is None:
        _out("没找到角色：%s" % char_name)
        return 1
    before = engine.card_mgr.card_of_character(char_name)
    cid = engine.card_mgr.get_or_create(card_name, source=CARD_SOURCE_MANUAL)
    if cid is None:
        _out("建卡失败：%s" % card_name)
        return 1
    ok = engine.card_mgr.attach_character(card_name, char_name)
    _kv("挂卡结果", [
        ("角色", row.get("name")),
        ("原卡", (before or {}).get("name") or "（未归卡）"),
        ("新卡", card_name),
        ("结果", "成功" if ok else "失败（角色已在别的卡上或参数非法）"),
    ])
    return 0 if ok else 1


def cmd_detach_card(args: Any) -> int:
    """``detach-card CHAR`` —— 把角色从卡上摘下来（角色本身不删）。"""
    engine = _open_engine(args)
    char_name = str(args.name or "").strip()
    if not char_name:
        _out("用法：python %s detach-card 角色名" % APP_NAME)
        return 2
    row = engine.char_mgr.get(char_name)
    if row is None:
        _out("没找到角色：%s" % char_name)
        return 1
    before = engine.card_mgr.card_of_character(char_name)
    if before is None:
        _out("角色 %s 本来就没挂在任何卡上。" % char_name)
        return 0
    ok = engine.card_mgr.detach_character(char_name)
    _kv("摘卡结果", [
        ("角色", row.get("name")),
        ("原卡", (before or {}).get("name")),
        ("结果", "成功" if ok else "失败"),
    ])
    return 0 if ok else 1


def cmd_migrate_card(args: Any) -> int:
    """``migrate-card NAME --card CARD [--into CHAR] [--role ROLE]``

    把"假卡角色"迁成真卡。两种力度：

    * 只给 ``--card``：把角色 NAME 挂到卡 CARD 下（卡不存在就建，
      ``source=manual``），**不建新卡、不动任何数据**。
    * 再给 ``--into CHAR``：把 NAME 名下的消息 / 记忆 / 信念 / 知识 /
      秘密 / 关系 / 关系历史 / 可见性 / 承诺 / 状态 全部改挂到 CHAR，
      然后把 NAME 从卡上摘除并置 ``active=0``。
      **一行都不物理删除**（V2 铁律 11）；唯一键冲突的行会保留在原角色上
      并如实报告。

    ``--role`` 用来顺手修正 NAME 的 ``role_type``（假卡角色通常是 unknown）。
    """
    engine = _open_engine(args)
    name = str(args.name or "").strip()
    card_name = str(args.card or "").strip()
    into = str(getattr(args, "into", "") or "").strip()
    role = str(getattr(args, "role", "") or "").strip()

    row = engine.char_mgr.get(name)
    if row is None:
        _out("没找到角色：%s" % name)
        return 1
    real_name = str(row.get("name") or name)
    before = engine.card_mgr.card_of_character(real_name)

    if role:
        if role not in VALID_ROLE_TYPES:
            _out("role 非法：%s（可选：%s）" % (role, "、".join(VALID_ROLE_TYPES)))
            return 2
        engine.set_role(real_name, role)
        _out("已把 %s 的角色类型改成 %s" % (real_name, role))

    # ---- 1) 挂卡（卡不存在就建，绝不把 NAME 本身建成卡）----
    if card_name:
        engine.card_mgr.get_or_create(card_name, source=CARD_SOURCE_MANUAL)
        engine.card_mgr.attach_character(card_name, real_name)
        _kv("挂卡", [("角色", real_name),
                    ("原卡", (before or {}).get("name") or "（未归卡）"),
                    ("新卡", card_name)])
    elif not into:
        _out("什么都没做（请给 --card，或 --into + --card）")
        return 2

    # ---- 2) 可选：把数据整体改挂到 CHAR ----
    moved: List[Any] = []
    if into:
        target = engine.char_mgr.get_or_create(into)
        if target is None:
            _out("目标角色无法建档：%s" % into)
            return 1
        tname = str(target.get("name") or into)
        if tname == real_name:
            _out("--into 与角色本身相同，跳过数据迁移")
            return 0
        src_id = _to_int(row.get("character_id"))
        dst_id = _to_int(target.get("character_id"))
        if dst_id is not None and card_name:
            engine.card_mgr.attach_character(card_name, tname)

        # 唯一键不冲突的：直接改挂
        simple = (
            ("messages", "character_id", "消息"),
            ("memories", "owner_character_id", "记忆"),
            ("knowledge", "owner_character_id", "知识"),
            ("beliefs", "owner_character_id", "信念"),
            ("secrets", "owner_character_id", "秘密"),
        )
        for table, col, label in simple:
            try:
                cur = engine.db.execute(
                    "UPDATE %s SET %s = ? WHERE %s = ?" % (table, col, col),
                    (dst_id, src_id))
                n = (cur.rowcount or 0) if cur is not None else 0
                if n:
                    moved.append((label, n))
            except Exception as ex:
                _out("  迁移 %s 失败：%s" % (label, ex))

        # 唯一键可能冲突的：UPDATE OR IGNORE，冲突行留在原角色上
        conflict = (
            ("event_visibility", "character_id", "可见性"),
            ("relationships", "from_character_id", "关系(出)"),
            ("relationships", "to_character_id", "关系(入)"),
            ("relationship_history", "from_character_id", "关系历史(出)"),
            ("relationship_history", "to_character_id", "关系历史(入)"),
            ("commitments", "promiser_id", "承诺(承诺者)"),
            ("commitments", "promisee_id", "承诺(受诺者)"),
            ("state_history", "character_id", "状态历史"),
        )
        for table, col, label in conflict:
            try:
                cur = engine.db.execute(
                    "UPDATE OR IGNORE %s SET %s = ? WHERE %s = ?"
                    % (table, col, col), (dst_id, src_id))
                n = (cur.rowcount or 0) if cur is not None else 0
                if n:
                    moved.append((label + "（跳过冲突）", n))
            except Exception as ex:
                _out("  迁移 %s 失败：%s" % (label, ex))

        # character_states 是主键，目标已有状态行就整块跳过
        try:
            has_dst = engine.db.query_one(
                "SELECT character_id FROM character_states "
                "WHERE character_id = ?", (dst_id,))
            if has_dst is None:
                cur = engine.db.execute(
                    "UPDATE OR IGNORE character_states SET character_id = ? "
                    "WHERE character_id = ?", (dst_id, src_id))
                n = (cur.rowcount or 0) if cur is not None else 0
                if n:
                    moved.append(("角色状态", n))
            else:
                _out("  目标角色已有状态行，%s 的状态保留未迁" % real_name)
        except Exception as ex:
            _out("  迁移 角色状态 失败：%s" % ex)

        # 只剩空壳的假卡角色：摘卡 + 停用（**不删行**）
        try:
            engine.card_mgr.detach_character(real_name)
            engine.char_mgr.set_active(real_name, False)
        except Exception as ex:
            _out("  停用 %s 失败：%s" % (real_name, ex))

        _kv("数据迁移", [("从", real_name), ("到", tname)] +
            (moved or [("结果", "没有需要迁移的行")]))
        _out("提示：消息 / 记忆已改挂到 %s；%s 的旧行仍保留（active=0），"
             "没有物理删除。" % (tname, real_name))
    return 0


def build_cli() -> argparse.ArgumentParser:
    """构造完整 CLI（SPEC「CLI 命令」段逐条对应）。"""
    epilog = (
        "示例：\n"
        "  python memory_full.py chat.jsonl                  快捷导入（= import）\n"
        "  python memory_full.py import chat.jsonl --mode deep\n"
        "  python memory_full.py context 甲 \"你昨晚去哪了\"\n"
        "  python memory_full.py memories 甲 --limit 20 --query 二楼\n"
        "  python memory_full.py serve --port 8081\n")
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="%s %s —— Tavo / SillyTavern 通用多角色长期记忆引擎"
                    % (APP_NAME, APP_VERSION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog)
    parser.add_argument("--version", "-V", action="version",
                        version="%s %s (schema v%s)"
                                % (APP_NAME, APP_VERSION, SCHEMA_VERSION))
    parser.add_argument("--db", metavar="PATH",
                        help="数据库路径（默认取 config 或 %s）" % DEFAULT_DB_PATH)
    parser.add_argument("--config", metavar="PATH",
                        help="配置文件（config.yaml / .yml / .json）")
    parser.add_argument("--debug", action="store_true",
                        help="DEBUG 日志（同时输出到 stderr）")

    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    # ---- init ----
    p = sub.add_parser("init", help="建库建表并打印统计")
    p.set_defaults(func=cmd_init)

    # ---- import ----
    p = sub.add_parser("import", help="导入聊天记录 JSONL 并增量抽取")
    p.add_argument("file", help="聊天记录文件（JSONL / JSON）")
    p.add_argument("--mode", choices=sorted(VALID_MODES), default=DEFAULT_MODE,
                   help="抽取模式（默认 %s）" % DEFAULT_MODE)
    p.add_argument("--limit", type=int, default=None, help="本次最多抽取多少条消息")
    p.add_argument("--no-process", action="store_true",
                   help="只导入，不做抽取")
    p.set_defaults(func=cmd_import)

    # ---- characters ----
    p = sub.add_parser("characters", help="角色列表")
    p.set_defaults(func=cmd_characters)

    # ---- detect-active ----
    p = sub.add_parser("detect-active", help="刷新活跃角色 + 核心角色候选")
    p.add_argument("--window", type=int, default=None, help="最近多少条消息")
    p.add_argument("--hours", type=float, default=None, help="最近多少小时")
    p.set_defaults(func=cmd_detect_active)

    # ---- memories ----
    p = sub.add_parser("memories", help="查看某角色的记忆")
    p.add_argument("name", help="角色名")
    p.add_argument("--limit", type=int, default=RETRIEVE_DEFAULT_LIMIT)
    p.add_argument("--query", "-q", default="", help="关键词检索")
    p.add_argument("--debug", action="store_true", help="输出评分明细")
    p.set_defaults(func=cmd_memories)

    # ---- relationships ----
    p = sub.add_parser("relationships", help="全库单向关系")
    p.set_defaults(func=cmd_relationships)

    # ---- set-relation-level ----
    p = sub.add_parser("set-relation-level",
                       help="手工把某关系维度设到指定层级（绕过 Δ 上限）")
    p.add_argument("--from", dest="from_name", required=True,
                   help="起方角色名")
    p.add_argument("--to", dest="to_name", required=True,
                   help="受方角色名，或 '用户'")
    p.add_argument("--dim", required=True, choices=list(ALLOWED_REL_FIELDS),
                   help="关系维度")
    p.add_argument("--level", required=True,
                   choices=sorted(META_LEVEL_VALUES), help="目标层级")
    p.add_argument("--reason", default="", help="原因文字（可选）")
    p.add_argument("--event-id", dest="event_id", type=int, default=None,
                   help="关联事件 ID（可选）")
    p.set_defaults(func=cmd_set_relation_level)

    # ---- state ----
    p = sub.add_parser("state", help="某角色当前状态 + 变更历史")
    p.add_argument("name", help="角色名")
    p.set_defaults(func=cmd_state)

    # ---- context ----
    p = sub.add_parser("context", help="生成某角色的上下文（含 Stance）")
    p.add_argument("name", help="角色名")
    p.add_argument("message", nargs="?", default="", help="当前这轮消息（用于检索排序）")
    p.add_argument("--debug", action="store_true")
    p.set_defaults(func=cmd_context)

    # ---- beliefs ----
    p = sub.add_parser("beliefs", help="某角色的信念")
    p.add_argument("name", help="角色名")
    p.add_argument("--kind", default=None,
                   choices=sorted(VALID_BELIEF_KINDS), help="按 kind 过滤")
    p.set_defaults(func=cmd_beliefs)

    # ---- visibility ----
    p = sub.add_parser("visibility", help="某角色知道 / 怀疑 / 听说过的事件")
    p.add_argument("name", help="角色名")
    p.add_argument("--event-id", type=int, default=None, help="只看某个事件")
    p.set_defaults(func=cmd_visibility)

    # ---- set-role ----
    p = sub.add_parser("set-role", help="设置角色类型（自动建档）")
    p.add_argument("name")
    p.add_argument("role", choices=sorted(VALID_ROLE_TYPES))
    p.set_defaults(func=cmd_set_role)

    # ---- set-profile ----
    p = sub.add_parser("set-profile", help="设置角色静态档案")
    p.add_argument("name")
    p.add_argument("--json", required=True, help="形如 '{\"外貌\":\"黑长直\"}'")
    p.set_defaults(func=cmd_set_profile)

    # ---- add-memory ----
    p = sub.add_parser("add-memory", help="手工写入一条记忆")
    p.add_argument("name")
    p.add_argument("content")
    p.add_argument("--type", dest="memory_type", default=DEFAULT_MEMORY_TYPE,
                   choices=sorted(VALID_MEMORY_TYPES))
    p.add_argument("--importance", type=float, default=DEFAULT_IMPORTANCE)
    p.add_argument("--emotion", type=float, default=DEFAULT_EMOTIONAL_INTENSITY)
    p.add_argument("--tag", action="append", default=None, help="可重复")
    p.add_argument("--source-type", dest="source_type",
                   default=DEFAULT_MEMORY_SOURCE_TYPE,
                   choices=sorted(VALID_MEMORY_SOURCES),
                   help="记忆来源（默认 %s）" % DEFAULT_MEMORY_SOURCE_TYPE)
    p.set_defaults(func=cmd_add_memory)

    # ---- add-belief ----
    p = sub.add_parser("add-belief", help="手工写入一条信念")
    p.add_argument("name")
    p.add_argument("--kind", required=True, choices=sorted(VALID_BELIEF_KINDS))
    p.add_argument("--subject-ref", dest="subject_ref", default=None)
    p.add_argument("--subject-kind", dest="subject_kind",
                   default=BELIEF_SUBJECT_FACT,
                   choices=sorted(VALID_BELIEF_SUBJECT_KINDS))
    p.add_argument("--statement", required=True)
    p.add_argument("--confidence", type=float, default=DEFAULT_BELIEF_CONFIDENCE)
    p.set_defaults(func=cmd_add_belief)

    # ---- add-knowledge ----
    p = sub.add_parser("add-knowledge", help="手工写入一条非事件型知识")
    p.add_argument("name")
    p.add_argument("subject")
    p.add_argument("--status", default=KN_KNOWN,
                   choices=sorted(VALID_KNOWLEDGE_STATUSES))
    p.add_argument("--confidence", type=float, default=0.5)
    p.set_defaults(func=cmd_add_knowledge)

    # ---- add-commitment ----
    p = sub.add_parser("add-commitment", help="手工写入一条承诺")
    p.add_argument("name", help="承诺者")
    p.add_argument("promisee", nargs="?", default=None, help="受诺者")
    p.add_argument("content")
    p.add_argument("--deadline", default=None, help="ISO-8601 时间")
    p.set_defaults(func=cmd_add_commitment)

    # ---- add-secret ----
    p = sub.add_parser("add-secret", help="手工写入一条秘密")
    p.add_argument("name")
    p.add_argument("content")
    p.add_argument("--subject", default="")
    p.set_defaults(func=cmd_add_secret)

    # ---- add-visibility ----
    p = sub.add_parser("add-visibility",
                       help="手工写可见性（默认 force=True）")
    p.add_argument("event_id", type=int, help="事件 id")
    p.add_argument("name", help="角色名")
    p.add_argument("--state", required=True,
                   choices=sorted(VALID_VISIBILITY_STATES))
    p.add_argument("--partial", default=None, help="SUSPECTED/RUMORED 必填")
    p.add_argument("--source", default=None,
                   help="firsthand / heard_from:X / inferred / witnessed_partially")
    p.add_argument("--source-message-id", dest="source_message_id", default=None)
    p.add_argument("--not-present", action="store_true", help="不在现场")
    p.set_defaults(func=cmd_add_visibility)

    # ---- consolidate ----
    p = sub.add_parser("consolidate", help="记忆压缩（原始记忆永不删除）")
    p.add_argument("--mode", choices=sorted(VALID_MODES), default=MODE_FAST,
                   help="fast=规则拼接 / normal|deep=LLM 摘要（默认 fast）")
    p.add_argument("--threshold", type=int, default=None)
    p.set_defaults(func=cmd_consolidate)

    # ---- extract ----
    p = sub.add_parser("extract", help="对未处理消息做增量抽取")
    p.add_argument("--mode", choices=sorted(VALID_MODES), default=DEFAULT_MODE)
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=cmd_extract)

    # ---- decay ----
    p = sub.add_parser("decay", help="记忆衰减")
    p.add_argument("--rate", type=float, default=None)
    p.set_defaults(func=cmd_decay)

    # ---- [V6 阶段D] merge-memories ----
    p = sub.add_parser(
        "merge-memories",
        help="安全聚合合并：粗筛 + LLM 终审（旧记忆只降级，绝不删除）")
    p.set_defaults(func=cmd_merge_memories)

    # ---- stats ----
    p = sub.add_parser("stats", help="全库统计")
    p.set_defaults(func=cmd_stats)

    # ---- serve ----
    p = sub.add_parser("serve", help="启动手机可用的记忆控制台")
    p.add_argument("--host", default=None, help="默认 %s" % DEFAULT_HOST)
    p.add_argument("--port", type=int, default=None, help="默认 %d" % DEFAULT_PORT)
    p.set_defaults(func=cmd_serve)

    # ---- V3 追加：卡片层 ----
    p = sub.add_parser("list-cards", help="列出所有卡 + 卡下角色数 + 记忆数")
    p.set_defaults(func=cmd_list_cards)

    p = sub.add_parser("attach-card", help="把已存在的角色挂到卡上")
    p.add_argument("name", help="角色名")
    p.add_argument("--card", required=True, help="卡名（不存在则新建）")
    p.set_defaults(func=cmd_attach_card)

    p = sub.add_parser("detach-card", help="把角色从卡上摘下来（不删角色）")
    p.add_argument("name", help="角色名")
    p.set_defaults(func=cmd_detach_card)

    p = sub.add_parser("migrate-card",
                       help="把「假卡角色」迁成真卡（--into 才搬数据）")
    p.add_argument("name", help="要迁移的角色名（通常是原来的假卡角色）")
    p.add_argument("--card", default=None, help="挂到哪张卡（不存在则新建）")
    p.add_argument("--into", default=None,
                   help="把该角色的消息/记忆整体改挂到这个角色（可选）")
    p.add_argument("--role", default=None, choices=sorted(VALID_ROLE_TYPES),
                   help="顺手修正该角色的 role_type（可选）")
    p.set_defaults(func=cmd_migrate_card)

    return parser


def cli(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 入口：返回进程退出码。

    ``python memory_full.py chat.jsonl`` 会自动展开成 ``import chat.jsonl``。
    """
    _force_utf8_stdout()
    raw = list(sys.argv[1:]) if argv is None else [str(a) for a in argv]
    raw = _normalize_shortcut(raw)

    parser = build_cli()
    args = parser.parse_args(raw)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0

    code = 0
    try:
        code = int(func(args) or 0)
    except KeyboardInterrupt:
        _out("\n已中断")
        code = 130
    except BrokenPipeError:
        code = 0
    except Exception as ex:
        logging.getLogger(APP_NAME).exception("[CLI] 命令失败：%s", ex)
        _out("命令执行失败：%s: %s" % (type(ex).__name__, ex))
        _out("（详细堆栈见 logs/%s）" % LOG_FILENAME)
        code = 1
    finally:
        engine = getattr(args, "engine_obj", None)
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass
    return code


# ==============================================================================
# 27. 入口
# ==============================================================================

if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())


# ==============================================================================
# 28. 使用文档
# ==============================================================================
#
# 以下是本文件的完整使用文档（SPEC「使用文档」段要求的 9 项）。
# 因为 argparse / 各 manager 都已在上面定义完毕，所以放在文件最末尾。
#
r"""
================================================================================
 memory_full.py 使用文档
 Tavo / SillyTavern 通用多角色长期记忆引擎（单文件 · 仅标准库）
================================================================================

设计上只有一条真理：

    事件发生了 ≠ 所有人知道了 ≠ 所有人记住了 ≠ 所有人相信了
             ≠ 所有人对它采取相同态度

所以系统把"客观事件"和"每个角色各自的主观认知"彻底分开存，任何角色
都只看得到自己的记忆 —— 不同角色之间不串记忆、不串认知。


================================================================================
 1. 环境安装
================================================================================

* Python 3.10 或更高（用到了 dataclass / 类型联合语法 / reconfigure）
* 无需任何第三方库；**只有想读 config.yaml 才需要 pyyaml**

    pip install pyyaml          # 可选，不装就只能读 config.json

* 本地 LLM（可选，想用 LLM 抽取/摘要时才需要）：
  任何 OpenAI 兼容服务都行，例如 llama.cpp：

    llama-server.exe -m 模型.gguf --port 8080 --ctx-size 8192

  LLM 关闭时一切照常工作，只是抽取退化为纯规则（关键词 + 正则 + 情绪词）。

目录约定：

    memory_full.py        主程序（单文件）
    SPEC.md               规格说明书（唯一权威）
    config.yaml           可选配置
    memory.db             SQLite 数据库（自动创建）
    logs/memory_full.log  运行日志（自动创建）


================================================================================
 2. 快速开始（三行命令）
================================================================================

    python memory_full.py chat.jsonl        # 1. 导入聊天记录并自动抽取记忆
    python memory_full.py context 甲     # 2. 看看角色现在"脑子里"有什么
    python memory_full.py serve              # 3. 手机浏览器打开控制台

第三条会打印本机与局域网地址，手机连同一个 Wi-Fi 直接访问即可：

    手机访问 : http://192.168.x.x:8081

想先不建库、只看参数：python memory_full.py --help


================================================================================
 3. 完整 CLI 参数表
================================================================================

全局参数（必须写在子命令**之前**）：

    --db PATH        数据库路径（默认 memory.db）
    --config PATH    配置文件（config.yaml / config.yml / config.json）
    --debug          DEBUG 日志，同时输出到 stderr
    --version, -V    显示版本
    --help, -h       帮助

子命令一览：

    命令                                       说明
    ------------------------------------------ ---------------------------------
    chat.jsonl                                 快捷写法，等价于 import chat.jsonl
    init                                       建库建表并打印统计
    import FILE [--mode fast|normal|deep]      导入 JSONL 并增量抽取
                 [--limit N] [--no-process]
    characters                                 角色列表（含消息/记忆/信念/知识数）
    detect-active [--window N] [--hours H]     刷新活跃角色 + 核心角色候选
    memories NAME [--limit N] [--query Q]      查看某角色的记忆
                  [--debug]
    relationships                              全库单向关系（谁对谁）
    state NAME                                 某角色当前状态 + 变更历史
    context NAME [MSG] [--debug]               生成角色上下文（含 Stance）
    beliefs NAME [--kind KIND]                 某角色的信念
    visibility NAME [--event-id ID]            该角色知道 / 怀疑 / 听说的事件
    set-role NAME ROLE                         user|main_character|npc|system|unknown
    set-profile NAME --json '{...}'            设置静态档案（外貌/性格/口癖…）
    add-memory NAME CONTENT [--type T]         手工写一条记忆
               [--importance F] [--emotion F] [--tag T]
    add-belief NAME --kind KIND                手工写一条信念
               --subject-ref REF --statement TEXT
               [--subject-kind K] [--confidence F]
    add-knowledge NAME SUBJECT [--status S]    手工写一条非事件型知识
                  [--confidence F]
    add-commitment NAME PROMISEE CONTENT       手工写一条承诺
                   [--deadline D]
    add-secret NAME CONTENT [--subject S]      手工写一条秘密
    add-visibility EVENT_ID NAME               手工写可见性（默认 force=True）
                   --state STATE [--partial TEXT]
                   [--source S] [--source-message-id MID]
    consolidate [--mode fast|normal|deep]      记忆压缩（原始记忆永不删除）
                [--threshold N]
    extract [--mode fast|normal|deep]          只对未处理消息做增量抽取
            [--limit N]
    decay [--rate F]                           记忆衰减（只降强度，不删记忆）
    stats                                      全库统计
    serve [--host H] [--port P]                启动 Web 控制台（默认 0.0.0.0:8081）

模式说明：

    fast     不调用 LLM，纯规则（快、零依赖、可离线）
    normal   有 LLM 就调 LLM，失败自动重试 2 次后回退规则
    deep     同 normal，但压缩时允许"二次整合"（摘要可以被再次压缩）


================================================================================
 4. HTTP API（serve 子命令）
================================================================================

全部为 GET 只读接口，返回 JSON（/ 除外）。默认 http://127.0.0.1:8081

    GET /                                     主控制台（角色列表 → 记忆卡片）
    GET /health                               健康检查
    GET /api/characters                       角色列表（含记忆/信念/知识计数）
    GET /api/memories/<name>?limit=100&q=...  某角色的记忆卡片
    GET /api/context/<name>?msg=...&debug=1   该角色的完整上下文文本
    GET /api/relationships                    全库单向关系
    GET /api/state/<name>                     当前状态 + 最近变更
    GET /api/beliefs/<name>?kind=BELIEF       信念（kind 可过滤）
    GET /api/visibility/<name>[?event_id=..]  该角色的可见性记录
    GET /api/stats                            全库统计

示例：

    curl http://127.0.0.1:8081/health
    curl "http://127.0.0.1:8081/api/characters"
    curl "http://127.0.0.1:8081/api/memories/甲?limit=20&q=二楼"
    curl "http://127.0.0.1:8081/api/context/甲?msg=你昨晚去哪了&debug=1"
    curl "http://127.0.0.1:8081/api/beliefs/甲?kind=ATTITUDE"
    curl "http://127.0.0.1:8081/api/visibility/甲"

页面：首页是角色列表（首字母头像 + 名字 + 角色类型 + 消息数 + 记忆数），
点进去是该角色的记忆卡片页（左上角"← 返回"，卡片带 memory_type 标签、
tags、评分、正文），顶部有搜索框。不引任何外部 CDN，无框架，手机可用。

Python 里当模块用：

    from memory_full import MemoryEngine
    eng = MemoryEngine("memory.db")
    print(eng.build_context("甲", "你昨晚去哪了"))
    print(eng.summary_stats())
    eng.close()


================================================================================
 5. config.yaml 示例
================================================================================

放在 memory_full.py 同目录（或任意目录用 --config 指过去）：

    db_path: memory.db
    debug: false
    host: 0.0.0.0
    port: 8081

    llm:
      enabled: false                    # true 才调 LLM
      base_url: http://127.0.0.1:8080/v1
      api_key: local
      model: local-model
      temperature: 0.2
      max_tokens: 1500
      timeout: 60

    memory:
      extraction_interval: 10           # 每批多少条消息抽一次
      max_context_memories: 20          # 上下文里最多带多少条记忆
      decay_enabled: true
      decay_rate: 0.01                  # 越重要/越情绪化的记忆衰减越慢
      consolidate_threshold: 5          # 同 owner 同类型攒够几条触发压缩
      auto_detect_main: true

同时支持 config.yml 与 config.json，路径顺序为：--config > 当前目录默认名。


================================================================================
 6. 数据模型速览（每张表一句话）
================================================================================

    characters            角色登记表（名字唯一，含 role_type / 别名 / 档案）
    messages              导入的原始聊天消息（message_id 主键 → 导入天然幂等）
    events                客观事件（第三人称摘要，不带任何角色立场）
    event_visibility      谁知道/怀疑/听说某个事件（KNOWN/SUSPECTED/RUMORED）
    memories              某个角色自己视角的记忆（owner_character_id 私有）
    knowledge             非事件型事实（"明喜欢吃苹果"），event_id 恒为 NULL
    beliefs               角色怎么理解（FACT/BELIEF/ATTITUDE/SELF_BELIEF/JUDGMENT）
    relationships         单向关系数值（甲→明 与 明→甲 是两条独立记录）
    relationship_history  关系每次调整的流水（谁改的、改了多少、为什么）
    character_states      角色自身当前状态（情绪/目标/位置…）
    state_history         状态每次变更的流水
    commitments           承诺（承诺者 / 受诺者 / 截止时间 / 状态）
    secrets               秘密（owner 私有，revealed_to 记录已告知对象）
    associations          记忆之间的关联（检索时沿关联带回相关记忆）
    event_chains          事件链（把同一线索的多个事件串起来）
    event_chain_links     事件与链的挂载关系（含顺序）
    memory_conflicts      记忆冲突记录（两条记忆打架时留档，等人工裁决）
    conversation_meta     键值元数据（schema 版本、导入游标等）

三条硬规则：

  * event_visibility 不写 UNKNOWN：完全不知道 = 没有任何记录
  * 记忆永不物理删除：遗忘只是 recall_strength 变小
  * character_states.trust/affection 是兼容字段，关系一律以 relationships 为准


================================================================================
 7. 单角色 / 多角色 / 新增角色
================================================================================

**单角色（赛博女友）**：导入聊天记录，给角色设个档案就够了。

    python memory_full.py chat.jsonl
    python memory_full.py set-role 甲 main_character
    python memory_full.py set-role 明 user
    python memory_full.py set-profile 甲 --json '{"外貌":"黑长直","性格":"外冷内热"}'
    python memory_full.py context 甲 "今天想我了吗"

**多角色（3~4 个或更多）**：每个角色各自消费自己的那份记录。

    python memory_full.py characters              # 看注册了哪些人
    python memory_full.py set-role 乙 npc
    python memory_full.py visibility 乙        # 她到底知道哪些事件
    python memory_full.py context 乙 "听说二楼出事了？"

**新增第 5 个角色**：不需要改任何代码。名字第一次出现在聊天记录里就自动
注册，之后它自动拥有自己的 memories / knowledge / beliefs /
relationships / visibility，与既有角色完全隔离。

    python memory_full.py set-role 王明远 npc     # 显式指定类型（可选）

隔离性自查：

    python -c "from memory_full import MemoryEngine; e=MemoryEngine(); print(e.audit_isolation('乙')); e.close()"

返回里的 foreign_count 必须是 0，forbidden_markers 必须是空列表。


================================================================================
 8. 常用工作流
================================================================================

【A. 每天追加聊天记录】

    1) 把新聊天记录导出成新的 JSONL
    2) python memory_full.py import new_chat.jsonl
       → 已存在的 message_id 自动跳过，只有新消息被抽取
    3) python memory_full.py stats

【B. 每周维护（建议做成定时任务）】

    python memory_full.py detect-active      # 刷新活跃角色
    python memory_full.py decay              # 时间衰减（重要记忆衰减极慢）
    python memory_full.py consolidate        # 把零散记忆压成摘要（原始不删）
    python memory_full.py extract            # 万一有漏抽的消息
    python memory_full.py stats

【C. 手工纠正/补充记忆】

    python memory_full.py add-memory 甲 "明答应过周末陪我去看海" \
        --type commitment --importance 0.9 --emotion 0.8
    python memory_full.py add-belief 甲 --kind ATTITUDE \
        --subject-ref 明 --statement "我对他有点不放心"
    python memory_full.py add-knowledge 甲 "明对花生过敏" --status KNOWN

【D. 手工指定"谁知道某个事件"】

    python memory_full.py add-visibility 12 甲 --state SUSPECTED \
        --partial "她只听到二楼传来一声闷响" --source inferred
    # SUSPECTED / RUMORED 必须给 --partial，否则拒绝写入
    # CLI 手工写入默认 force=True；LLM 提案没有新来源时会被降级拦截

【E. 让角色接上下文】

    python memory_full.py context 甲 "你昨晚去哪了？" --debug

把输出的文本塞进你的角色卡 prompt 即可。其中【当前行为倾向】是每次
实时推导的 Stance，**不落库**，所以不会污染长期记忆。

【F. 冲突裁决】

    python memory_full.py memories 甲 --query 二楼
    冲突会写进 memory_conflicts，永不自动删除旧记忆；
    需要人工判断后走 resolve_conflict() 决定 superseded / contradicted。


================================================================================
 9. V1 → V2 迁移提示
================================================================================

1) 数据库可以直接复用（V2 全部使用 CREATE TABLE IF NOT EXISTS，不会删表），
   但强烈建议先备份：copy memory.db memory.v1.bak

2) `knowledge.event_id` 变成**兼容字段**：V2 不再通过它把事件型知识塞进
   knowledge，新写入的非事件型 knowledge 一律 event_id = NULL。
   V1 留下的历史行会原样保留，不会被改写。

3) `character_states.trust / affection` 变成**兼容字段**：它们不再是关系
   真相源。所有"对某人的信任/好感"请读 relationships 表。V2 的
   ContextBuilder / RelationshipManager 一律忽略这两个字段。

4) 认知模型升级：V1 里"谁不知道"可能是靠状态值表达的，V2 改为
   **UNKNOWN 不落库** —— 完全不知道就是没有任何 event_visibility 记录。

5) 新增单调性约束：event_visibility 只升不降（RUMORED < SUSPECTED < KNOWN），
   升级必须伴随新的 source_message_id / source / event_id，或 force=True。
   历史数据本身不受影响，但后续 LLM 提案不会再"把已知改成怀疑"。

6) 新增记忆压缩：consolidate 只处理 is_consolidated = 0 的原始记忆，
   原始记忆一律保留（status 变 weakened，recall_strength 减半），
   摘要不会被反复套娃压缩（除非 --mode deep 显式允许）。

7) 迁移后建议依次跑一遍：

    python memory_full.py stats
    python memory_full.py detect-active
    python memory_full.py extract --mode fast
    python memory_full.py consolidate --mode fast
    python memory_full.py serve

--------------------------------------------------------------------------------
 一句话：新增角色不改代码，导入重复不出脏数据，记忆永不物理删除，
         每个角色只看得到自己的记忆。坏行/网络/LLM 全部容错，绝不崩。
================================================================================
"""
