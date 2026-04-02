#!/bin/bash
# ========================================================
# 自动日报工具 - Crontab 一键部署脚本
# ========================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CRONTAB_BAK="/tmp/crontab.bak.$(date +%s)"

echo "=========================================="
echo "自动日报工具 - Crontab 部署"
echo "=========================================="
echo "项目根目录: $PROJECT_ROOT"
echo ""

# 检查是否在正确的目录
if [ ! -f "$PROJECT_ROOT/config.yaml" ]; then
    echo "❌ 错误: 未找到 config.yaml，请确认在项目根目录下运行"
    exit 1
fi

# 备份当前 crontab
echo "📋 备份当前 crontab..."
crontab -l > "$CRONTAB_BAK" 2>/dev/null || true
echo "   备份已保存到: $CRONTAB_BAK"
echo ""

# 检查是否已配置
echo "🔍 检查现有配置..."
CRONTAB_CONTENT=$(crontab -l 2>/dev/null || true)
HAS_DAILY_REPORT=$(echo "$CRONTAB_CONTENT" | grep -c "daily_report.py.*--yesterday" || true)
HAS_TOKEN_REFRESH=$(echo "$CRONTAB_CONTENT" | grep -c "python.*-m feishu.*refresh" || true)

echo ""
echo "当前状态:"
if [ "$HAS_TOKEN_REFRESH" -gt 0 ]; then
    echo "  ✅ Token 刷新任务: 已配置"
else
    echo "  ❌ Token 刷新任务: 未配置"
fi
if [ "$HAS_DAILY_REPORT" -gt 0 ]; then
    echo "  ✅ 日报生成任务: 已配置"
else
    echo "  ❌ 日报生成任务: 未配置"
fi
echo ""

# 询问用户
if [ "$HAS_TOKEN_REFRESH" -gt 0 ] || [ "$HAS_DAILY_REPORT" -gt 0 ]; then
    read -p "⚠️  检测到已存在配置，是否继续? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消操作"
        exit 0
    fi
    echo ""
fi

# 生成新的 crontab 配置
echo "✏️  生成新配置..."

NEW_CRONTAB=$(cat <<EOF
$CRONTAB_CONTENT

# ========================================================
# 自动日报工具
# ========================================================
# Token 刷新: 每天凌晨 1 点（确保 refresh_token 永续）
0 1 * * * cd $PROJECT_ROOT && python -m feishu refresh --quiet

# 日报生成: 每天凌晨 2 点生成前一天的日报
0 2 * * * cd $PROJECT_ROOT && python daily_report.py --yesterday
EOF
)

# 清理重复的空行
NEW_CRONTAB=$(echo "$NEW_CRONTAB" | sed '/^$/N;/^\n$/D')

echo ""
echo "新配置预览:"
echo "----------------------------------------"
echo "$NEW_CRONTAB" | tail -20
echo "----------------------------------------"
echo ""

read -p "❓ 确认部署? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "取消操作"
    exit 0
fi

# 应用配置
echo ""
echo "🚀 应用新配置..."
echo "$NEW_CRONTAB" | crontab -

echo ""
echo "✅ 部署成功!"
echo ""
echo "验证配置:"
echo "----------------------------------------"
crontab -l
echo "----------------------------------------"
echo ""
echo "📌 提示:"
echo "  - 查看日志: 配置文件中的日志输出位置"
echo "  - 临时禁用: crontab -e 注释掉相关行"
echo "  - 卸载: crontab -r (会清除所有 crontab)"
echo "  - 恢复备份: crontab $CRONTAB_BAK"
echo ""
