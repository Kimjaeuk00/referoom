import os
import sys
from pathlib import Path

# 앱(config_rag)을 import하기 전에 설정해야 한다. tests/rag/conftest.py와 같은 값이어야
# 두 폴더를 함께 실행해도 RAG 테스트의 토큰 검증이 어긋나지 않는다
os.environ["JWT_SECRET"] = "test-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
