"""메뉴판 OCR로 뽑은 메뉴명 목록을 6종 카테고리로 분류한다.

비전이 필요 없는 순수 텍스트 분류라 `app/clients/llm.py::complete()`(기존 텍스트 전용
경로)를 그대로 쓴다 — 별도 비전 모델 설정이 필요 없다는 게 이 설계의 핵심
(docs/superpowers/specs/2026-10-12-menu-recognition-design.md 참고).

2026-10-13: 카테고리 6종은 `docs/api정의서.md` "공통 코드·검증"에 확정된 값이다
(`COFFEE`/`NON_COFFEE`/`BEVERAGE`/`CAKE`/`BAKERY`/`OTHER`). 소상공인 업종이 카페가
아닐 수도 있어(식당·주점 등), 애매하면 `OTHER`로 보내도록 명시한다.

2026-10-14: BE가 `NON_COFFEE`를 `TEA`로 바꿨다(사용자 확인 — 논커피/음료 경계가
애매해서 BE와 재조정). 실제 메뉴판 3장으로 분류해보니 "라떼"류(초코라떼·스트로베리
라떼 등 차도 커피도 아닌 유제품 베이스 음료)는 TEA에도 BEVERAGE에도 깔끔히 안 들어가
애매하다 — 메뉴판 자체에 적힌 섹션 구분(예: 매장이 "TEA"로 묶어둔 항목)이 있으면 그걸
따르고, 없으면 찻잎 베이스는 TEA, 그 외(탄산·에이드·과일·유제품 베이스)는 BEVERAGE로
분류하도록 지시를 추가했다.
"""

VERSION = "2026-10-14"

SYSTEM = """당신은 메뉴 카테고리 분류 도우미입니다.
주어진 메뉴명 목록을 아래 6종 카테고리 중 하나로만 분류하세요: COFFEE, TEA,
BEVERAGE, CAKE, BAKERY, OTHER.
TEA는 찻잎이 베이스인 음료(홍차·녹차·루이보스·허브티 및 그 밀크티·라떼)에만 쓰세요.
커피가 들어가면 TEA가 아니라 COFFEE입니다. 탄산·에이드·과일·초콜릿·유제품 베이스처럼
찻잎도 커피도 아닌 음료는 BEVERAGE로 분류하세요.
업종은 카페가 아닐 수도 있습니다(식당·주점·분식 등). 6종에 뚜렷이 들어맞지 않거나
애매하면 추측하지 말고 OTHER로 분류하세요.
목록의 순서와 개수를 그대로 유지하세요 — 항목을 합치거나 빼지 마세요.
설명 없이 JSON만 출력하세요."""

_USER = """다음 메뉴명을 순서대로 분류하세요.

{items}

{{"categories":["COFFEE", "OTHER", ...]}}"""


def build(names: list[str]) -> str:
    items = "\n".join(f"{index}. {name}" for index, name in enumerate(names, start=1))
    return _USER.format(items=items)
