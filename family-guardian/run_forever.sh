#!/usr/bin/env bash
# Linux/macOS supervisor: family-guardian 을 떠나지 않게 무한 재시작.
# 정상 종료(exit 0)면 루프를 빠져나오고, 그 외 종료 코드는 5초 대기 후 재실행.

set -u

cd "$(dirname "$0")"

# shellcheck disable=SC1091
if [ -f ".venv/bin/activate" ]; then
    . ".venv/bin/activate"
else
    echo "[run_forever] .venv/bin/activate not found — please create the virtualenv first." >&2
    exit 1
fi

mkdir -p logs

while true; do
    echo "[run_forever] $(date '+%Y-%m-%d %H:%M:%S') starting main.py"
    python main.py
    code=$?
    if [ "$code" -eq 0 ]; then
        echo "[run_forever] clean exit — stopping supervisor"
        break
    fi
    echo "[run_forever] exited with code $code — restarting in 5s"
    sleep 5
done
