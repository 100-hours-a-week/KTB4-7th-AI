"""연속 실패를 세서 "지금 primary를 건너뛸지"만 판단하는 작은 상태 기계.

HTTP·LLM을 전혀 모른다 — 호출자(app/clients/llm.py)가 성공/실패를 알려주고
`should_skip()`으로 지금 건너뛰어야 하는지만 물어본다. 세 상태를 왔다 갔다 한다.

    CLOSED --(연속 실패 threshold회)--> OPEN --(cooldown 경과)--> HALF_OPEN
      ^                                                              |
      |----------------------(probe 성공)---------------------------|
                               (probe 실패) --> OPEN(쿨다운 재시작)

메서드는 전부 sync다. asyncio 단일 이벤트 루프에서 await 없이 상태를 읽고 쓰므로
경쟁 조건이 없다 — 락이 필요 없다. 프로세스 하나 기준 상태라 워커를 여러 개로
늘리면 각자 따로 추적한다(지금 배포 규모에서는 문제 없다고 보고 넘긴다).
"""

import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock  # 테스트가 진짜 시간을 안 기다리게 주입할 수 있게 뺐다.
        self._consecutive_failures = 0
        self._open_until: float | None = None
        # OPEN 상태에서 쿨다운이 지나 half-open 판정을 "한 번만" 요청자에게 알려주기
        # 위한 플래그. 같은 half-open 기회를 여러 요청이 동시에 더블로 쓰지 않게 한다.
        self._probing = False

    @property
    def probing(self) -> bool:
        return self._probing

    def should_skip(self) -> bool:
        """지금 primary를 건너뛰고 바로 fallback으로 가야 하면 True.

        OPEN 이고 쿨다운이 아직 안 지났으면 건너뛴다. 쿨다운이 지났으면 "probe 한 번"을
        허용하기 위해 False를 돌려주되(= 이번 호출은 primary를 시도해 보라는 뜻),
        내부적으로 probing 상태로 바꿔 둔다 — 그 결과는 `record_success`/`record_failure`가
        받아서 breaker를 닫거나 쿨다운을 다시 연다.
        """
        if self._probing:
            # 이미 다른 요청이 이 half-open 기회를 쓰고 있다 — 그 결과(record_success/
            # record_failure)가 나오기 전까지는 동시 요청을 전부 fallback으로 보낸다.
            return True
        if self._open_until is None:
            return False
        if self._clock() < self._open_until:
            return True
        self._probing = True
        return False

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._open_until = None
        self._probing = False

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        was_probing = self._probing
        self._probing = False
        if was_probing or self._consecutive_failures >= self._failure_threshold:
            self._open_until = self._clock() + self._cooldown_seconds
