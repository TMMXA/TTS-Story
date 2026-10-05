"""Language-aware reference voice defaults without loading a speech model."""

from __future__ import annotations

import re
from typing import Any, Mapping


CHINESE_STANDARD_PREVIEW_TEXT = (
    "当你听到这段声音时，应该能够清楚地感受到我的语气和声音特点。"
    "也许它与你最初想象的并不完全相同。请仔细听，"
    "我会从安静而克制的思考，逐渐转向清晰、坚定而有力量的表达。"
)
CHINESE_SPEAKER_PROFILE_PROMPT = (
    "分析中文小说中每个指定角色，严格保留提供的角色标签和姓名。"
    "仅使用原文支持的身份、经历与关系，未知的信息注明未知，不能把猜测当作事实。"
    "Full Description 用中文描述长期身份、年龄、性别、性格与作用；"
    "Voice Type 用中文描述稳定的音高、音域、音色、声音质感、节奏和长期说话习惯，"
    "不使用当前一句的愤怒、哭喊、悲伤等临时情绪作为声线。"
    "Voice Design Prompt 使用简洁的英文合成指令，明确性别和年龄、稳定音色、语速，"
    "包含 Standard Mandarin（标准普通话），不得默认英语口音。"
    "不要从中文姓名猜测性别；根据原文证据推断，未知时使用 GENDER-NEUTRAL。"
)
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\U00020000-\U0003134f]")


def resolve_voice_language(payload: Mapping[str, Any]) -> str:
    """Prefer explicit voice language, project language, then source script."""
    settings = payload.get("novel_settings") or {}
    for candidate in (payload.get("voice_design_language"), payload.get("language"), settings.get("language")):
        value = str(candidate or "").strip()
        if value and value.lower() != "auto":
            return {"zh": "Chinese", "zh-cn": "Chinese", "zh-hans": "Chinese",
                    "en": "English", "ja": "Japanese", "ko": "Korean"}.get(value.lower(), value.title())
    source = " ".join(str(payload.get(key) or "") for key in ("text", "processed_text", "voice_type", "voice"))
    if re.search(r"[\u3040-\u30ff]", source):
        return "Japanese"
    if re.search(r"[\uac00-\ud7af]", source):
        return "Korean"
    if _HAN.search(source):
        return "Chinese"
    return "English"


def pad_voice_preview(text: str, language: str = "Auto", *, minimum_words: int = 40) -> str:
    """Pad short casting text in its own language, counting CJK characters."""
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return cleaned
    if _CJK.search(cleaned) or language.lower() in {"chinese", "japanese", "korean"}:
        padding = {
            "japanese": "この声の響きや話す速さを、落ち着いて聞いてください。静かな思いから、はっきりした力強い表現へと進んでいきます。",
            "korean": "이 목소리의 음색과 말하는 속도를 차분하게 들어 주세요. 조용한 생각에서 또렷하고 힘 있는 표현으로 이어집니다.",
        }.get(language.lower(), CHINESE_STANDARD_PREVIEW_TEXT)
        while len(_CJK.findall(cleaned)) < 60:
            cleaned = f"{cleaned.rstrip()} {padding}"
        return cleaned
    padding = (
        "The speaker continues with clear articulation and natural pacing, moving from calm reflection "
        "through firm conviction and rising urgency to demonstrate a believable emotional range for audiobook dialogue."
    )
    while len(cleaned.split()) < minimum_words:
        cleaned = f"{cleaned.rstrip()} {padding}"
    return cleaned


def default_voice_accent(language: str) -> str:
    return {"Chinese": "Standard Mandarin", "Japanese": "Standard Japanese accent",
            "Korean": "Standard Korean accent"}.get(language, "Neutral English accent")


def chinese_voice_gender(source: str) -> str | None:
    if re.search(r"女声|女性|少女|女孩|女人|女童|老妇", source):
        return "female"
    if re.search(r"男声|男性|少年|男孩|男人|男童|老翁", source):
        return "male"
    if re.search(r"中性|性别中立", source):
        return "neutral"
    return None


def chinese_voice_age(source: str) -> str | None:
    age = re.search(r"(\d{1,2})\s*岁", source)
    if age:
        years = int(age.group(1))
        return ("child" if years <= 12 else "teenage" if years <= 17 else
                "young_adult" if years <= 29 else "elderly" if years >= 65 else
                "middle_aged" if years >= 45 else "adult")
    for pattern, category in ((r"儿童|童声|男童|女童|小孩", "child"),
                              (r"少年|少女|青少年", "teenage"),
                              (r"青年|年轻", "young_adult"),
                              (r"中年", "middle_aged"), (r"老年|老人|老者|苍老", "elderly")):
        if re.search(pattern, source):
            return category
    return None
