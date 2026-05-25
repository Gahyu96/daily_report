#!/bin/bash
set -e

# 测试日期
DATE="2026-04-16"
START="${DATE}T00:00:00+08:00"
END="${DATE}T23:59:59+08:00"

echo "================================================================================
测试 1: 不指定 chat-type
================================================================================"
lark-cli im +messages-search \
    --start "$START" \
    --end "$END" \
    --page-size 50 \
    --page-all \
    --format ndjson | wc -l

echo ""
echo "================================================================================
测试 2: 指定 chat-type=group
================================================================================"
lark-cli im +messages-search \
    --start "$START" \
    --end "$END" \
    --chat-type group \
    --page-size 50 \
    --page-all \
    --format ndjson | wc -l

echo ""
echo "================================================================================
测试 3: 指定 chat-type=p2p
================================================================================"
lark-cli im +messages-search \
    --start "$START" \
    --end "$END" \
    --chat-type p2p \
    --page-size 50 \
    --page-all \
    --format ndjson | wc -l
