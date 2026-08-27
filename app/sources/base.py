from abc import ABC, abstractmethod
from datetime import datetime, timezone
import time
from typing import Dict, List

from requests import exceptions as requests_exceptions

from app.core.logger import get_logger
from app.source_coverage import record_collector_health


logger = get_logger("采集器")

MAX_COLLECT_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5
RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class CollectorUnavailable(RuntimeError):
    """采集器因缺少必要配置或访问条件而没有真正执行。"""


def _retryable_error(error: Exception) -> bool:
    """只重试明确的瞬时网络/上游错误，避免代码错误被重复执行。"""
    if isinstance(
        error,
        (requests_exceptions.Timeout, requests_exceptions.ConnectionError),
    ):
        return True

    if isinstance(error, requests_exceptions.HTTPError):
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        return status in RETRYABLE_HTTP_STATUS

    return False


class BaseCollector(ABC):
    """所有情报采集器的公共接口。"""

    name = "unknown"

    def _set_health(
        self,
        *,
        success: bool,
        attempts: int,
        result_count: int = 0,
        error: str = "",
        available: bool = True,
        partial: bool = False,
    ) -> None:
        self.last_run_health = {
            "collector": self.__class__.__name__,
            "source": str(getattr(self, "name", "unknown") or "unknown"),
            "success": bool(success),
            "available": bool(available),
            "partial": bool(partial),
            "attempts": max(int(attempts or 0), 0),
            "result_count": max(int(result_count or 0), 0),
            "error": str(error or ""),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        # 复用子类 get_last_health()，因此 PolicyCollector 可以把机构级覆盖状态
        # 一并写入当前运行快照。健康记录失败不能反向影响业务采集。
        try:
            record_collector_health(
                str(getattr(self, "name", "unknown") or "unknown"),
                self.get_last_health(),
            )
        except Exception:
            logger.exception(
                "采集健康状态记录失败：采集器=%s",
                self.__class__.__name__,
            )

    def get_last_health(self) -> Dict:
        """返回最近一次 collect_safe 的轻量健康状态，不包含密钥或业务正文。"""
        return dict(getattr(self, "last_run_health", {}) or {})

    def collect_safe(self, *args, **kwargs) -> List[Dict]:
        """安全执行采集器；瞬时网络错误最多自动重试一次，并区分空结果、不可用、部分降级与失败。"""
        for attempt in range(1, MAX_COLLECT_ATTEMPTS + 1):
            # partial 属于单次尝试的覆盖状态。重试必须从干净状态开始，避免第一次失败留下假降级。
            self.collection_partial = False
            self.collection_partial_reason = ""

            try:
                result = self.collect(*args, **kwargs)

                # 先校验类型再判断空值；空 dict / 空 tuple 不能被误记为“成功 0 条”。
                if not isinstance(result, list):
                    self._set_health(
                        success=False,
                        attempts=attempt,
                        error=f"返回类型无效：{type(result).__name__}",
                    )
                    logger.warning(
                        "采集器返回类型无效：采集器=%s 类型=%s",
                        self.__class__.__name__,
                        type(result).__name__,
                    )
                    return []

                partial = bool(getattr(self, "collection_partial", False))
                partial_reason = str(getattr(self, "collection_partial_reason", "") or "")

                if not result:
                    self._set_health(
                        success=True,
                        attempts=attempt,
                        result_count=0,
                        partial=partial,
                        error=partial_reason,
                    )
                    return []

                self._set_health(
                    success=True,
                    attempts=attempt,
                    result_count=len(result),
                    partial=partial,
                    error=partial_reason,
                )
                return result

            except CollectorUnavailable as error:
                # 缺少 Token/权限与“查询成功但 0 条”语义完全不同；不重试，也不打印异常堆栈。
                self._set_health(
                    success=False,
                    available=False,
                    attempts=attempt,
                    error=str(error),
                )
                logger.warning(
                    "采集器当前不可用：采集器=%s 原因=%s",
                    self.__class__.__name__,
                    error,
                )
                return []

            except Exception as error:
                can_retry = (
                    attempt < MAX_COLLECT_ATTEMPTS
                    and _retryable_error(error)
                )
                if can_retry:
                    logger.warning(
                        "采集器瞬时失败，准备重试：采集器=%s 尝试=%s/%s 错误=%s",
                        self.__class__.__name__,
                        attempt,
                        MAX_COLLECT_ATTEMPTS,
                        error,
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue

                self._set_health(
                    success=False,
                    attempts=attempt,
                    error=f"{type(error).__name__}: {error}",
                )
                logger.exception(
                    "采集器执行失败：采集器=%s 尝试=%s/%s",
                    self.__class__.__name__,
                    attempt,
                    MAX_COLLECT_ATTEMPTS,
                )
                return []

        self._set_health(
            success=False,
            attempts=MAX_COLLECT_ATTEMPTS,
            error="超过最大采集尝试次数",
        )
        return []

    @abstractmethod
    def collect(self, *args, **kwargs) -> List[Dict]:
        pass