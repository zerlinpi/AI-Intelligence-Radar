from typing import Dict, List

import os

from app.sources.base import BaseCollector


class ProductHuntCollector(BaseCollector):
    name = "producthunt"

    def collect(self, limit: int = 10) -> List[Dict]:
        """
        Product Hunt collection remains disabled until API credentials
        are configured. Keep the collector safe so the main pipeline can
        continue when this source is unavailable.
        """
        token = os.getenv("PRODUCT_HUNT_TOKEN", "").strip()

        if not token:
            return []

        # Placeholder for the existing Product Hunt API integration path.
        # Do not fail the daily pipeline when credentials are unavailable.
        return []


def fetch_producthunt(limit: int = 10):
    return ProductHuntCollector().collect_safe(limit)
