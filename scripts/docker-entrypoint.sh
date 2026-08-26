#!/bin/sh
set -e

# 启动应用前先执行数据库迁移。
if [ -f scripts/migrate_db.py ]; then
  echo "正在执行数据库迁移..."
  python scripts/migrate_db.py || {
    echo "数据库迁移失败"
    exit 1
  }
fi

echo "正在启动 AI 情报雷达..."
exec "$@"
