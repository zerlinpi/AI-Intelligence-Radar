def test_project_smoke_import():
    import app.pipeline
    import app.scoring
    import app.models.radar_item

    assert app.pipeline is not None
    assert app.scoring is not None
