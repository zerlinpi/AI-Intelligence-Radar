def calculate_score(item):
    stars = item.get("stargazers_count", 0)
    forks = item.get("forks_count", 0)

    score = (
        min(stars / 1000, 40)
        + min(forks / 100, 20)
        + 20
        + 20
    )

    return round(min(score, 100), 2)
