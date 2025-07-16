
import pytest

import modules.database as database
from app import app


def test_upload_get():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200


def test_history_get(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)
    database.init_db()
    client = app.test_client()
    response = client.get('/history')
    assert response.status_code == 200
