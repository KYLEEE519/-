import json
from pathlib import Path
import pytest
from equitybot.providers import DemoProvider
from equitybot.storage import Store
@pytest.fixture
def cfg(): return json.loads(Path('config.json').read_text())
@pytest.fixture
def raw(): return DemoProvider().load('2026-10-23')
@pytest.fixture
def store(tmp_path): return Store(tmp_path)
