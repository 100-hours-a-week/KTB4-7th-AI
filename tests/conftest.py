"""테스트는 개발자 `.env` 를 읽지 않는다.

`Settings` 가 `env_file=".env"` 라서, 테스트가 명시하지 않은 필드는 그 기계의 `.env` 에서
채워진다. 그래서 `test_health.py` 의 `missing_required` 테스트들이 **기계마다 결과가
달랐다** — 로컬 LLM 작업을 하는 기계는 `LLM_BASE_URL` 이 있어서 `uses_local_llm_server`
가 True 가 되고 API 키 요구가 사라진다(2026-11-04 확인). `.env` 가 없는 CI 에서만
통과해서 오래 안 걸렸다.
"""

import pytest

from app.core.config import Settings


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(Settings.model_config, "env_file", None)
