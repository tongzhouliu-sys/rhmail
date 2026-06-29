#!/bin/sh
set -e

LOWER_SERVICE_NAME=$(echo "${RAILWAY_SERVICE_NAME:-}" | tr '[:upper:]' '[:lower:]')
LOWER_JOB=$(echo "${JOB:-}" | tr '[:upper:]' '[:lower:]')

if [ "$LOWER_JOB" = "fetch" ] || [ "$LOWER_JOB" = "digest" ] || [ "$LOWER_JOB" = "sync" ]; then
    echo "🤖 [Entrypoint] 识别到环境变量 JOB=$LOWER_JOB，准备启动独立 Task..."
    exec python3 -m app.jobs "$LOWER_JOB"
elif echo "$LOWER_SERVICE_NAME" | grep -qE "cron|job|fetch|worker"; then
    echo "🤖 [Entrypoint] 识别到 Railway 服务名称为 '$RAILWAY_SERVICE_NAME' (Cron/Worker 服务)，准备启动邮件同步..."
    exec python3 -m app.jobs fetch

fi

# 默认启动 Web 服务
exec "$@"
