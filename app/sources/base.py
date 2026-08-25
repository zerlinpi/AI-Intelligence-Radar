from abc import ABC, abstractmethod
from typing import List, Dict

from app.core.logger import get_logger


logger = get_logger("collector")


class BaseCollector(ABC):
    """Common interface for all intelligence data collectors."""

    name = "unknown"

    def collect_safe(self) -> List[Dict]:
        """Run collector safely and always return a list."""
        try:
            result = self.collect()

            if not result:
                return []

            if not isinstance(result, list):
                logger.warning(
                    "collector=%s returned invalid type=%s",
                    self.__class__.__name__,
                    type(result).__name__,
                )
                return []

            return result

        except Exception:
            logger.exception(
                "collector execution failed=%s",
                self.__class__.__name__,
            )
            return []

    @abstractmethod
    def collect(self) -> List[Dict]:
        pass
