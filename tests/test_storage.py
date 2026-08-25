from app.storage.repository import save_batch


class FakeQuery:
    def __init__(self, exists):
        self._exists = exists

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return object() if self._exists else None


class FakeDB:
    def __init__(self):
        self.items = []

    def query(self, _model):
        return FakeQuery(False)

    def add(self, item):
        self.items.append(item)

    def commit(self):
        pass

    def refresh(self, _item):
        pass


def test_repository_save_batch_deduplicates_with_existing_url(monkeypatch):
    db = FakeDB()

    monkeypatch.setattr(
        "app.storage.repository.exists",
        lambda _db, url: url == "https://example.com/existing",
    )

    result = save_batch(
        db,
        [
            {"title": "Existing", "url": "https://example.com/existing"},
            {"title": "New", "url": "https://example.com/new"},
        ],
    )

    assert len(result) == 1
