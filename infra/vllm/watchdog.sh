#!/bin/bash
# serve.sh(vLLM)가 죽거나(크래시·OOM) 응답이 멈추면(health check 실패) 재기동한다.
# RunPod Pod는 컨테이너라 systemd가 PID 1이 아니고(docker-init), cron도 없어서
# nohup 루프로 대신한다. VLLM_API_KEY는 serve.sh와 동일하게 미리 export해둬야 한다.
#
# 여기서 못 잡는 것: Pod 자체가 재시작되는 경우(이 스크립트도 같이 죽는다) —
# Pod 시작 커맨드를 바꾸려면 stop이 필요한데, A40 재고 부족으로 재가동이 안 될
# 위험이 있어 지금은 그 리스크를 감수하지 않는다. 수동 대응 영역으로 남겨둔다.
cd "$(dirname "$0")"
LOG=/root/vllm_watchdog.log
HEALTH_URL="http://localhost:8000/health"
MAX_UNHEALTHY=3          # health check 실패 허용 횟수 (20초 간격 * 3 = 약 60초)
MIN_RESTART_INTERVAL=30  # 재시도 최소 간격 — 반복 실패(OOM 등)로 로그가 폭주하지 않게

restart_count=0

while true; do
  echo "$(date -Iseconds) vLLM 기동 시도 (누적 재시작 ${restart_count}회)" >> "$LOG"
  ./serve.sh >> /root/vllm_serve.log 2>&1 &
  serve_pid=$!

  unhealthy=0
  while kill -0 "$serve_pid" 2>/dev/null; do
    sleep 20
    if curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -q 200; then
      unhealthy=0
    else
      unhealthy=$((unhealthy + 1))
      echo "$(date -Iseconds) health check 실패 (${unhealthy}/${MAX_UNHEALTHY})" >> "$LOG"
      if [ "$unhealthy" -ge "$MAX_UNHEALTHY" ]; then
        echo "$(date -Iseconds) health check 연속 실패 — 프로세스 강제 종료" >> "$LOG"
        kill -9 "$serve_pid" 2>/dev/null
        break
      fi
    fi
  done

  wait "$serve_pid" 2>/dev/null
  restart_count=$((restart_count + 1))
  echo "$(date -Iseconds) vLLM 종료 감지(누적 ${restart_count}회) — ${MIN_RESTART_INTERVAL}초 후 재기동" >> "$LOG"
  sleep "$MIN_RESTART_INTERVAL"
done
