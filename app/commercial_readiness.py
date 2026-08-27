import re
from typing import Dict


# 这里只做 Radar 的产品筛选，不替代法律意见。
# permissive：通常允许商业使用并以保留版权/NOTICE 等条件为主；
# conditional：通常允许商业使用，但存在更强的开源、网络分发或专有条款义务；
# restricted：材料明确出现 Non-Commercial / Research-Only 等商业限制；
# unknown：公开元数据没有足够许可证信息。
PERMISSIVE_LICENSES = {
    "mit",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "zlib",
    "unlicense",
    "cc0-1.0",
}

CONDITIONAL_LICENSE_PREFIXES = (
    "gpl-",
    "agpl-",
    "lgpl-",
    "mpl-",
    "epl-",
    "cddl-",
    "osl-",
    "openrail",
    "creativeml-openrail",
    "llama",
    "gemma",
)

RESTRICTED_LICENSE_MARKERS = (
    "noncommercial",
    "non-commercial",
    "research-only",
    "research only",
    "academic-only",
    "academic only",
    "cc-by-nc",
    "cc-by-nc-sa",
    "cc-by-nc-nd",
    "polyform-noncommercial",
)

# 只有明确表达“使用限制”的自然语言才作为补充证据；
# 不能因为正文讨论 academic research 就把普通开源项目误判为 Research-Only。
RESTRICTED_TEXT_PATTERNS = (
    re.compile(r"\b(?:for\s+)?non[- ]commercial\s+(?:use|purposes?)\s+only\b", re.IGNORECASE),
    re.compile(r"\bresearch\s+(?:use|purposes?)\s+only\b", re.IGNORECASE),
    re.compile(r"\bacademic\s+(?:use|purposes?)\s+only\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:for|licensed\s+for)\s+commercial\s+(?:use|purposes?)\b", re.IGNORECASE),
    re.compile(r"\bcommercial\s+use\s+(?:is\s+)?(?:not\s+permitted|prohibited|forbidden)\b", re.IGNORECASE),
)

UNKNOWN_LICENSE_MARKERS = {
    "",
    "unknown",
    "noassertion",
    "other",
    "none",
}


def _metrics(item: Dict) -> dict:
    value = item.get("metrics") if isinstance(item, dict) else None
    return value if isinstance(value, dict) else {}


def _normalize_license(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("_", "-")
    return re.sub(r"\s+", "-", text)


def _hf_license(item: Dict) -> str:
    metrics = _metrics(item)
    direct = _normalize_license(metrics.get("license") or item.get("license"))
    if direct not in UNKNOWN_LICENSE_MARKERS:
        return direct

    tags = metrics.get("tags") or item.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    for raw in tags:
        tag = str(raw or "").strip()
        if tag.lower().startswith("license:"):
            value = _normalize_license(tag.split(":", 1)[1])
            if value:
                return value
    return ""


def _github_license(item: Dict) -> str:
    metrics = _metrics(item)
    return _normalize_license(metrics.get("license_spdx") or item.get("license_spdx"))


def _classify_license(license_name: str) -> str:
    value = _normalize_license(license_name)
    if value in UNKNOWN_LICENSE_MARKERS:
        return "unknown"
    if any(marker in value for marker in RESTRICTED_LICENSE_MARKERS):
        return "restricted"
    if value in PERMISSIVE_LICENSES:
        return "permissive"
    if any(value.startswith(prefix) for prefix in CONDITIONAL_LICENSE_PREFIXES):
        return "conditional"
    # 已公开许可证但不在安全白名单中，不武断判为禁止商用。
    return "conditional"


def _explicit_text_restriction(item: Dict) -> bool:
    text = " ".join(str((item or {}).get("description") or "").split())
    return bool(text and any(pattern.search(text) for pattern in RESTRICTED_TEXT_PATTERNS))


def commercial_readiness(item: Dict) -> Dict:
    """返回用于产品筛选的许可证/商业复用状态。

    该函数只根据公开元数据与明确使用限制判断“是否值得进入产品候选”，
    不对许可证具体法律义务作最终解释。部署或销售前仍应核对原始 LICENSE / Model Card。
    """
    item = item if isinstance(item, dict) else {}
    source = str(item.get("source") or "").strip().lower()

    if source == "github":
        license_name = _github_license(item)
    elif source == "huggingface":
        license_name = _hf_license(item)
    else:
        return {
            "status": "not_applicable",
            "license": "",
            "commercial_candidate": True,
            "direct_reuse_ready": False,
            "score": 50,
            "reason": "该来源不使用代码/模型许可证作为前置筛选条件",
        }

    status = _classify_license(license_name)

    # LICENSE 元数据未知时，README / Model Card 中非常明确的限制语句可作为兜底；
    # 若 SPDX 已明确为 MIT/Apache 等，则不让正文的一般 research 措辞覆盖许可证事实。
    if status == "unknown" and _explicit_text_restriction(item):
        status = "restricted"

    if status == "permissive":
        return {
            "status": status,
            "license": license_name,
            "commercial_candidate": True,
            "direct_reuse_ready": True,
            "score": 100,
            "reason": "公开许可证通常适合商业复用，仍需遵守署名/NOTICE等具体条款",
        }
    if status == "conditional":
        return {
            "status": status,
            "license": license_name,
            "commercial_candidate": True,
            "direct_reuse_ready": False,
            "score": 70,
            "reason": "许可证存在开源披露或专有使用条件，产品化前需核对具体义务",
        }
    if status == "restricted":
        return {
            "status": status,
            "license": license_name,
            "commercial_candidate": False,
            "direct_reuse_ready": False,
            "score": 0,
            "reason": "公开许可证或项目说明包含明确非商业/研究用途限制",
        }

    # GitHub 无许可证仍可能有很强的架构/产品参考价值，但不能声称代码可直接商用；
    # Hugging Face 模型若许可证未知，则不进入“可用于商品”的模型候选。
    if source == "huggingface":
        return {
            "status": "unknown",
            "license": "",
            "commercial_candidate": False,
            "direct_reuse_ready": False,
            "score": 20,
            "reason": "模型许可证未知，无法确认可用于商业产品",
        }
    return {
        "status": "unknown",
        "license": "",
        "commercial_candidate": True,
        "direct_reuse_ready": False,
        "score": 40,
        "reason": "仓库许可证未知，只能作为技术/产品参考，不能假设代码可直接商业复用",
    }


def _evidence_line(result: Dict) -> str:
    status = str(result.get("status") or "unknown")
    license_name = str(result.get("license") or "").strip() or "未知"
    if status == "permissive":
        return f"商业许可:{license_name}，可作为商业复用候选，仍需核对具体条款"
    if status == "conditional":
        return f"商业许可:{license_name}，可商用但存在许可证义务，集成前需核对"
    if status == "restricted":
        return f"商业许可:{license_name}，存在明确非商业/研究用途限制"
    if status == "unknown":
        return "商业许可:未知，不得假设代码或模型可直接商业复用"
    return ""


def attach_commercial_metrics(item: Dict, result: Dict | None = None) -> Dict:
    item = item if isinstance(item, dict) else {}
    result = result or commercial_readiness(item)
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        item["metrics"] = metrics

    metrics["commercial_license_status"] = result.get("status", "unknown")
    metrics["commercial_license"] = result.get("license", "")
    metrics["commercial_candidate"] = bool(result.get("commercial_candidate", False))
    metrics["commercial_direct_reuse_ready"] = bool(result.get("direct_reuse_ready", False))
    metrics["commercial_readiness_score"] = int(result.get("score", 0) or 0)
    metrics["commercial_readiness_reason"] = str(result.get("reason") or "")

    # analyzer 已经把 opportunity_evidence 作为“据=”发送给 DeepSeek；
    # 在这里复用现有字段，避免再扩大模型协议，同时确保许可风险进入最终判断。
    evidence = metrics.get("opportunity_evidence") or []
    evidence = list(evidence) if isinstance(evidence, list) else []
    line = _evidence_line(result)
    evidence = [value for value in evidence if not str(value).startswith("商业许可:")]
    if line:
        evidence.insert(0, line)
    metrics["opportunity_evidence"] = evidence
    return item
