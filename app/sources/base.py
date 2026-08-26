from abc import ABC, abstractmethod
from typing import List, Dict

from app.core.logger import get_logger


logger = get_logger("采集器")


class BaseCollector(ABC):
    """所有情报采集器的公共接口。"""

    name = "unknown"

    def collect_safe(self, *args, **kwargs) -> List[Dict]:
        """安全执行采集器，并确保始终返回列表。"""
        try:
            result = self.collect(*args, **kwargs)

            if not result:
                return []

            if not isinstance(result, list):
                logger.warning(
                    "采集器返回类型无效：采集器=%s 类型=%s",
                    self.__class__.__name__,
                    type(result).__name__,
                )
                return []

            return result

        except Exception:
            logger.exception(
                "采集器执行失败：采集器=%s",
                self.__class__.__name__,
            )
            return []

    @abstractmethod
    def collect(self, *args, **kwargs) -> List[Dict]:
        pass
