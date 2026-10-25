#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/dev/cli.sh"

main() {
    local command="${1:-help}"
    case "$command" in
        help|-h|--help)
            if [ "$#" -gt 1 ]; then
                dev_error '도움말 명령에는 추가 인자를 사용할 수 없습니다.'
                return 2
            fi
            dev_usage
            ;;
        setup|init-env|up|down|status|logs|restart|test)
            if command -v uv >/dev/null 2>&1; then
                exec uv --no-cache run --offline --no-project --python python3.11 python "$SCRIPT_DIR/dev/manager.py" "$@"
            elif command -v python3.11 >/dev/null 2>&1; then
                exec python3.11 "$SCRIPT_DIR/dev/manager.py" "$@"
            else
                dev_error 'Python 3.11이 필요합니다. uv 또는 python3.11 설치를 확인하세요.'
                return 1
            fi
            ;;
        *)
            dev_error '지원하지 않는 명령입니다. scripts/dev.sh --help를 확인하세요.'
            return 2
            ;;
    esac
}

main "$@"
