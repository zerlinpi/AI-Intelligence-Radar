from abc import ABC, abstractmethod
from typing import List, Dict


class BaseCollector(ABC):
    """Common interface for all intelligence data collectors."""

    name = "unknown"

    def collect_safe(self) -> List[Dict]:
        try:
            result = self.collect()
            return result if result else []
        except Exception:
            return []

    @abstractmethod
    def collect(self) -> List[Dict]:
        pass
