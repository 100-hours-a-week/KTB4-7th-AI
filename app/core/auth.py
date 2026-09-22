"""선택적 내부 토큰 검증.

2026-09-16 팀 결정은 "앱 레벨 인증 없음, 인바운드를 BE 로만 제한하는 보안 그룹이 경계"였고
그 결정은 유효하다. 여기서 되살린 건 **보안 그룹이 설정되지 않았을 때를 대비한 두 번째
방어선**이지 그 결정을 뒤집는 게 아니다 — 보안 그룹 요구사항은 2026-09-22 까지 코드 주석에만
있었고 인프라에 반영됐는지 아무도 확인하지 않았다. AI 서버가 외부에 열리면 인증 없이 LLM 을
호출할 수 있게 되고, 그건 곧바로 요금이다.

**INTERNAL_AI_TOKEN 이 비어 있으면 검증하지 않는다.** 필수로 두면 배포 때 BE 와 AI 의
시크릿이 어긋나는 순간 전부 401 이 되어 연동 테스트 당일을 통째로 막는다. 클라우드팀이
이미 병목이라 새 실패 모드를 그 경로에 얹지 않는다. 연동이 끝난 뒤 양쪽에 주입하면
그때부터 검증이 켜진다.

BE 는 `Authorization: Bearer {INTERNAL_AI_TOKEN}` 로 보낸다(2026-09-22 계약).
"""

import hmac

from fastapi import Request

from app.core.config import settings
from app.core.errors import ApiError

_PREFIX = "Bearer "


async def verify_internal_token(request: Request) -> None:
    expected = settings.internal_ai_token
    if not expected:
        return

    header = request.headers.get("authorization", "")
    if not header.startswith(_PREFIX):
        raise ApiError(401, "UNAUTHORIZED", "내부 인증 토큰이 필요합니다.")

    # 타이밍 공격 방지. 토큰이 짧아 실익은 작지만 비교 비용도 같이 작다.
    if not hmac.compare_digest(header[len(_PREFIX) :], expected):
        raise ApiError(401, "UNAUTHORIZED", "내부 인증 토큰이 올바르지 않습니다.")
