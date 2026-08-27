from datetime import datetime, timezone
from typing import Dict


EDGE_DEPLOYMENT_SIGNALS = (
    "onnx",
    "onnxruntime",
    "tflite",
    "tensorflow-lite",
    "tensorflow lite",
    "coreml",
    "openvino",
    "ncnn",
    "tensorrt",
    "executorch",
    "webgpu",
    "gguf",
    "mlx",
    "int8",
    "int4",
    "quantized",
    "quantization",
    "microcontroller",
    "mcu",
    "esp32",
    "jetson",
    "rk3588",
    "raspberry pi",
)


def _metrics(item: Dict) -> dict:
    value = item.get("metrics") if isinstance(item, dict) else None
    return value if isinstance(value, dict) else {}


def _number(value) -> float:
    try:
        return max(float(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _parse_time(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(item: Dict) -> str:
    metrics = _metrics(item)
    parts = [str(item.get("title") or ""), str(item.get("description") or "")]
    for key in ("tags", "topics", "pipeline_tag", "library_name", "language"):
        value = metrics.get(key)
        if isinstance(value, list):
            parts.extend(str(part) for part in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _deployment_signals(item: Dict) -> list:
    text = _text(item)
    return [signal for signal in EDGE_DEPLOYMENT_SIGNALS if signal in text]


def _list_metric(metrics: dict, key: str) -> list:
    value = metrics.get(key) or []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def github_engineering_readiness(item: Dict) -> Dict:
    metrics = _metrics(item)
    if bool(metrics.get("archived")) or bool(metrics.get("disabled")):
        return {
            "eligible": False,
            "score": 0,
            "reason": "仓库已归档或禁用，不作为当前产品开发候选",
            "evidence": [],
        }

    size_kb = _number(metrics.get("repo_size_kb", metrics.get("size_kb")))
    readme_chars = int(_number(metrics.get("readme_chars")))
    readme = bool(metrics.get("readme_evidence")) and readme_chars > 0
    language = bool(str(metrics.get("language") or "").strip())
    homepage = bool(str(metrics.get("homepage") or "").strip())
    license_status = str(metrics.get("commercial_license_status") or "unknown").strip().lower()
    lane = str(metrics.get("primary_lane") or "").strip()

    tree_evidence = bool(metrics.get("engineering_tree_evidence"))
    repo_file_count = int(_number(metrics.get("repo_file_count")))
    code_file_count = int(_number(metrics.get("repo_code_file_count")))
    package_configs = _list_metric(metrics, "package_config_files")
    deployment_files = _list_metric(metrics, "deployment_files")
    test_files = _list_metric(metrics, "test_files")
    ci_files = _list_metric(metrics, "ci_files")

    latest_release_tag = str(metrics.get("latest_release_tag") or "").strip()
    release_published = _parse_time(metrics.get("latest_release_published_at"))
    recent_commit_checked = bool(metrics.get("recent_commit_activity_checked"))
    recent_commit_count = int(_number(metrics.get("recent_commit_sample_count")))
    commit_window_days = int(_number(metrics.get("recent_commit_window_days"))) or 14

    pushed = _parse_time(metrics.get("pushed_at"))
    push_age_hours = None
    active = False
    if pushed is not None:
        push_age_hours = max((datetime.now(timezone.utc) - pushed).total_seconds() / 3600, 0)
        active = push_age_hours <= 14 * 24

    score = 0
    evidence = []

    if language:
        score += 20
        evidence.append(f"主要语言:{metrics.get('language')}")
    if readme:
        score += 25 if readme_chars >= 500 else 18
        evidence.append(f"README证据:{readme_chars}字符")
    if size_kb >= 100:
        score += 22
        evidence.append(f"仓库体量:{int(size_kb)}KB")
    elif size_kb >= 20:
        score += 16
        evidence.append(f"仓库体量:{int(size_kb)}KB")
    elif size_kb >= 5:
        score += 8
        evidence.append(f"仓库体量:{int(size_kb)}KB")

    # commits API 成功时，以默认分支真实提交样本替代 pushed_at 的间接活跃度证据。
    # API增强不可用时仍回退 pushed_at，避免限流导致误杀。
    if recent_commit_checked:
        if recent_commit_count >= 5:
            score += 18
        elif recent_commit_count >= 2:
            score += 13
        elif recent_commit_count == 1:
            score += 7
        if recent_commit_count:
            evidence.append(f"近{commit_window_days}天默认分支提交样本:{recent_commit_count}")
        else:
            evidence.append(f"近{commit_window_days}天默认分支未发现提交")
    elif active:
        score += 18
        evidence.append("近14天有代码提交")

    # 正式 Release 是“有人维护 + 有可消费版本”的强工程信号，但不能替代代码/文件树/许可条件。
    if latest_release_tag:
        score += 8
        evidence.append(f"正式Release:{latest_release_tag}")
        if release_published is not None:
            release_age_days = max(
                (datetime.now(timezone.utc) - release_published).total_seconds() / 86400,
                0,
            )
            if release_age_days <= 30:
                score += 4
                evidence.append("Release近30天")

    if license_status == "permissive":
        score += 12
    elif license_status == "conditional":
        score += 7
    elif license_status == "unknown":
        score += 2
    if homepage:
        score += 3

    # 文件树增强是比仓库 size/language 更直接的工程资产证据。只有请求成功时才启用这些判断，
    # 因此 GitHub API 限流或瞬时失败不会把原本合格的候选误伤。
    if tree_evidence:
        if code_file_count >= 20:
            score += 10
        elif code_file_count >= 5:
            score += 7
        elif code_file_count >= 2:
            score += 3
        evidence.append(f"文件树:{repo_file_count}文件/{code_file_count}代码文件")

        if package_configs:
            score += 7
            evidence.append("包/构建配置:" + "/".join(package_configs[:3]))
        if deployment_files:
            score += 5
            evidence.append("部署配置:" + "/".join(deployment_files[:3]))
        if test_files:
            score += 4
            evidence.append("测试资产:存在")
        if ci_files:
            score += 4
            evidence.append("CI资产:存在")

        # GitHub 元数据的 language/size 可能被 notebook、二进制或文档资源放大；
        # 文件树已经成功读取时，以真实代码文件数量作为更强的反证。
        if code_file_count < 2:
            return {
                "eligible": False,
                "score": min(score, 100),
                "reason": "文件树证据显示实际代码文件不足，不能仅凭README、仓库体量或热度判为可开发项目",
                "evidence": evidence,
                "push_age_hours": round(push_age_hours, 1) if push_age_hours is not None else None,
            }

    # README 只是说明材料，不等于代码。至少要看到一定仓库体量，并配合语言或 README 证据。
    # 这能排除 README-only、概念页、营销仓库，即使它们有 Star 或写得很完整。
    has_real_asset = size_kb >= 5 and (language or readme)
    if not has_real_asset:
        return {
            "eligible": False,
            "score": min(score, 100),
            "reason": "缺少足够代码体量，README或热度本身不能证明可开发性",
            "evidence": evidence,
        }

    # 开发基础设施和硬件候选要求更高：需要明确代码语言，并达到可复用工程资产体量。
    if lane in {"开发基础设施", "实体商品/硬件"} and not (language and size_kb >= 20):
        return {
            "eligible": False,
            "score": min(score, 100),
            "reason": "工程/硬件候选缺少足够代码资产或主要开发语言，暂不进入产品开发雷达",
            "evidence": evidence,
        }

    if tree_evidence and lane in {"开发基础设施", "实体商品/硬件"} and code_file_count < 5:
        return {
            "eligible": False,
            "score": min(score, 100),
            "reason": "工程/硬件候选的文件树代码资产过少，暂不足以作为可复用开发基础",
            "evidence": evidence,
            "push_age_hours": round(push_age_hours, 1) if push_age_hours is not None else None,
        }

    # 新仓库允许提交时间缺失，但如果明确有 pushed_at，则必须保持活跃。
    if pushed is not None and not active:
        return {
            "eligible": False,
            "score": min(score, 100),
            "reason": "仓库近期无代码活动，不作为当前开发机会",
            "evidence": evidence,
        }

    return {
        "eligible": score >= 35,
        "score": min(score, 100),
        "reason": (
            "具备可验证的代码文件、版本/提交活动、工程说明和配置资产"
            if tree_evidence and (latest_release_tag or recent_commit_count) and score >= 35
            else "具备可验证的代码文件、工程说明、配置资产和近期开发活动"
            if tree_evidence and score >= 35
            else "具备可验证的代码资产、工程说明和近期开发活动"
            if score >= 35
            else "工程成熟度不足"
        ),
        "evidence": evidence,
        "push_age_hours": round(push_age_hours, 1) if push_age_hours is not None else None,
    }


def huggingface_deployment_readiness(item: Dict) -> Dict:
    metrics = _metrics(item)
    lane = str(metrics.get("primary_lane") or "").strip()
    model_card_chars = int(_number(metrics.get("model_card_chars")))
    model_card = bool(metrics.get("model_card_evidence")) and model_card_chars > 0
    pipeline_tag = str(metrics.get("pipeline_tag") or "").strip()
    library_name = str(metrics.get("library_name") or "").strip()
    license_status = str(metrics.get("commercial_license_status") or "unknown").strip().lower()
    signals = _deployment_signals(item)

    score = 0
    evidence = []
    if model_card:
        score += 35 if model_card_chars >= 500 else 25
        evidence.append(f"Model Card:{model_card_chars}字符")
    if pipeline_tag:
        score += 12
        evidence.append(f"任务:{pipeline_tag}")
    if library_name:
        score += 10
        evidence.append(f"框架:{library_name}")
    if signals:
        score += min(30, 10 + len(signals) * 4)
        evidence.append("部署信号:" + "/".join(signals[:6]))
    if license_status == "permissive":
        score += 13
    elif license_status == "conditional":
        score += 8

    # 没有 Model Card 时，不把模型任务标签本身当成“可用于产品”的证据。
    if not model_card:
        return {
            "eligible": False,
            "score": min(score, 100),
            "reason": "缺少Model Card，无法验证模型用途、限制和部署条件",
            "evidence": evidence,
        }

    # 硬件/实体商品候选必须出现真实端侧/量化/推理部署证据。
    if lane == "实体商品/硬件" and not signals:
        return {
            "eligible": False,
            "score": min(score, 100),
            "reason": "硬件候选缺少ONNX/TFLite/量化/端侧推理等部署证据",
            "evidence": evidence,
        }

    return {
        "eligible": score >= 45,
        "score": min(score, 100),
        "reason": "模型用途、商业许可和部署路径具备可验证证据" if score >= 45 else "模型部署成熟度不足",
        "evidence": evidence,
    }


def deployment_readiness(item: Dict) -> Dict:
    source = str((item or {}).get("source") or "").strip().lower()
    if source == "github":
        return github_engineering_readiness(item)
    if source == "huggingface":
        return huggingface_deployment_readiness(item)
    return {
        "eligible": True,
        "score": 50,
        "reason": "该来源不使用代码/模型部署成熟度作为前置门槛",
        "evidence": [],
    }


def attach_deployment_metrics(item: Dict, result: Dict | None = None) -> Dict:
    item = item if isinstance(item, dict) else {}
    result = result or deployment_readiness(item)
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        item["metrics"] = metrics

    metrics["deployment_ready"] = bool(result.get("eligible"))
    metrics["deployment_readiness_score"] = int(result.get("score", 0) or 0)
    metrics["deployment_readiness_reason"] = str(result.get("reason") or "")
    # 证据单独持久化，避免 relevance 重新生成 opportunity_evidence 时丢失工程事实。
    metrics["deployment_evidence"] = [
        str(value).strip()
        for value in (result.get("evidence") or [])
        if str(value or "").strip()
    ]
    if result.get("push_age_hours") is not None:
        metrics["repo_push_age_hours"] = result.get("push_age_hours")

    evidence = metrics.get("opportunity_evidence") or []
    evidence = list(evidence) if isinstance(evidence, list) else []
    evidence = [value for value in evidence if not str(value).startswith("部署成熟度:")]
    evidence_line = str(result.get("reason") or "").strip()
    if evidence_line:
        evidence.insert(0, f"部署成熟度:{evidence_line}")
    for detail in metrics["deployment_evidence"]:
        if detail not in evidence:
            evidence.append(detail)
    metrics["opportunity_evidence"] = evidence
    return item
