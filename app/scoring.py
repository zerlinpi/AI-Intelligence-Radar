def calculate_score(item):
    """Calculate normalized trend score from unified RadarItem fields."""
    stars = item.get("stars", 0) or 0
    forks = item.get("forks", 0) or 0
    comments = item.get("comments", 0) or 0
    downloads = item.get("downloads", 0) or 0
    upvotes = item.get("upvotes", 0) or 0

    score = (
        min(stars / 1000, 35)
        + min(forks / 100, 20)
        + min(comments / 50, 15)
        + min(downloads / 10000, 15)
        + min(upvotes / 20, 15)
    )

    return round(min(score, 100), 2)
