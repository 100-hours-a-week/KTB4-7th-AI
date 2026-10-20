#!/bin/bash
# RunPod A40에서 vLLM(Qwen3-32B-AWQ)을 기동하는 커맨드. 매번 Pod를 새로 만들 때
# 설정이 누락돼 측정값·운영 동작이 달라지는 문제(3차, docs/STATE.md)를 막으려고
# 레포에 고정해둔다. 기존 vLLM 프로세스가 떠 있으면 먼저 kill해야 한다 — 안 내리고
# 띄우면 GPU 메모리가 겹쳐 CUDA out of memory로 죽는다(docs/STATE.md 2026-10-16).
set -euo pipefail

: "${VLLM_API_KEY:?VLLM_API_KEY를 먼저 export하세요 — 클라우드팀 요청 인증값}"

# ninja 부재로 기본 flashinfer 샘플러가 JIT 빌드에 실패해 우회한다(6차, PR #189).
export VLLM_USE_FLASHINFER_SAMPLER=0

vllm serve Qwen/Qwen3-32B-AWQ --port 8000 --quantization awq_marlin \
  --max-model-len 8192 --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --api-key "${VLLM_API_KEY}"
