#!/bin/zsh
# Daily Report Cron Wrapper - 加载环境变量后执行命令

# 加载 zsh 配置（包含环境变量）
source "$HOME/.zshrc"

# 切换到项目目录
cd "$HOME/projects/daily_report" || exit 1

# 执行传入的命令
exec "$@"
