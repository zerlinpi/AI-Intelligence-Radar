from app.sources.base import BaseCollector


class ProductHuntCollector(BaseCollector):
    name = "producthunt"

    def collect(self, limit=10):
        # Product Hunt requires API credentials for official access.
        # Keep this collector safe until PRODUCT_HUNT_TOKEN is configured.
        return []


def fetch_producthunt():
    return ProductHuntCollector().collect_safe()
