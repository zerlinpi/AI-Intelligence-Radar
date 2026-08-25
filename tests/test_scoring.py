from app.scoring import calculate_score


def test_score_range():
    score = calculate_score({
        "stars": 10000,
        "forks": 1000,
        "comments": 500,
        "downloads": 100000,
        "upvotes": 500,
    })

    assert 0 <= score <= 100


def test_more_popular_item_scores_higher():
    low = calculate_score({"stars": 10})
    high = calculate_score({"stars": 10000})

    assert high > low
