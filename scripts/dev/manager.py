"""Local development lifecycle. No external Python packages required."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

CHILDREN = {}  # Retain/reap supervisors started in this invocation.
SERVICES = ("db", "auth", "rag", "voice", "frontend")
PORTS = dict(zip(SERVICES, (53301, 8080, 8001, 8008, 5174)))
DEFAULTS = dict(DB_HOST="localhost", DB_PORT="53301", DB_NAME="sql_db", DB_USER="root",
                FRONTEND_URL="http://localhost:5174",
                CORS_ALLOWED_ORIGINS="http://localhost:5174,http://localhost:8008")
SHARED = ("JWT_SECRET", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
          "FRONTEND_URL", "CORS_ALLOWED_ORIGINS")


class DevError(Exception):
    pass


def say(message):
    print(message, flush=True)


def dotenv(path):
    """Read literal dotenv values; never execute shell or expand substitutions."""
    values = {}
    if not path.is_file():
        return values
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise DevError(f"{path.name}:{number}: KEY=VALUE 형식이 필요합니다 (값 비노출).")
        key, value = match.groups()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].strip().startswith("#")):
                raise DevError(f"{path.name}:{number}: 한 줄 따옴표 값을 확인하세요 (값 비노출).")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def service_env(root, service):
    local = dotenv(root / f"{service}-service/.env") if service in ("rag", "voice") else {}
    if service == "auth":
        local = dotenv(root / "auth-server/.env")
    if service == "frontend":
        local = dotenv(root / "frontend/.env")
    shared = dotenv(root / "auth-server/.env")
    common = dotenv(root / ".env")
    # Process > root > auth defaults for shared settings. Per-service files never split JWT.
    env = {**DEFAULTS, **common, **local, **os.environ}
    for key in SHARED:
        value = os.environ.get(key, common.get(key, shared.get(key, DEFAULTS.get(key))))
        if value is not None:
            env[key] = value
    env.setdefault("RAG_URL", "http://localhost:8001")
    if service == "rag":
        # 개발 환경은 실제 색인(local)을 쓴다. 비워 두면 RAG가 가짜 저장소(stub)로 떠서 라이브러리 API가 503이 되고 답변도 가짜 자료로 나온다
        env.setdefault("RAG_STORE", "local")
    return env


def redactor(root):
    values = set()
    for file in [root / ".env", root / "auth-server/.env", root / "rag-service/.env",
                 root / "voice-service/.env", root / "frontend/.env"]:
        for key, value in dotenv(file).items():
            if value and any(word in key.upper() for word in ("SECRET", "PASSWORD", "API_KEY", "TOKEN")):
                values.add(value)
    for key, value in os.environ.items():
        if value and any(word in key.upper() for word in ("SECRET", "PASSWORD", "API_KEY", "TOKEN")):
            values.add(value)
    def redact(text):
        for value in sorted(values, key=len, reverse=True):
            text = text.replace(value, "[REDACTED]")
        text = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", text)
        return text
    return redact


def state_dir(root):
    path = root / ".run"
    path.mkdir(mode=0o700, exist_ok=True)
    for name in ("pids", "logs", "setup"):
        (path / name).mkdir(mode=0o700, exist_ok=True)
    return path


@contextlib.contextmanager
def locked(root):
    with (state_dir(root) / "dev.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DevError("다른 dev 명령이 진행 중입니다.") from None
        yield


def record_path(root, service):
    return root / ".run/pids" / f"{service}.json"


def read_record(root, service):
    try:
        return json.loads(record_path(root, service).read_text())
    except (FileNotFoundError, ValueError):
        return None


def identity(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart=", "-o", "command="],
                            text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def owned(root, record):
    if not isinstance(record, dict) or record.get("root") != str(root):
        return False
    pid = record.get("pid")
    if type(pid) is not int or pid <= 1:
        return False
    current = identity(pid)
    try:
        return bool(current and current == record.get("identity") and os.getpgid(pid) == pid)
    except ProcessLookupError:
        return False


def occupied(port):
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.15):
                return True
        except OSError:
            pass
    return False


def require_tool(name):
    import shutil
    path = shutil.which(name)
    if not path:
        raise DevError(f"필요한 도구가 없습니다: {name}")
    return path


def py_for(root, service):
    path = root / f"{service}-service/.venv/bin/python"
    if not path.is_file():
        raise DevError(f"{service} 가상환경이 없습니다. scripts/dev.sh setup을 먼저 실행하세요.")
    return str(path)


def commands(root, service):
    if service in ("rag", "voice"):
        return root / f"{service}-service", [py_for(root, service), "-m", "uvicorn", "app.main:app",
                                                    "--host", "127.0.0.1", "--port", str(PORTS[service])]
    if service == "auth":
        wrapper = root / "auth-server/gradlew"
        if not wrapper.is_file():
            raise DevError("auth-server/gradlew가 없습니다.")
        require_tool("java")
        return wrapper.parent, ["/bin/bash", str(wrapper), ":app:bootRun", "--no-daemon"]
    require_tool("npm")
    if not (root / "frontend/node_modules").is_dir():
        raise DevError("프론트 의존성이 없습니다. scripts/dev.sh setup을 먼저 실행하세요.")
    return root / "frontend", ["npm", "run", "dev", "--", "--host", "127.0.0.1",
                               "--port", "5174", "--strictPort"]


def capture(root, args, cwd=None, env=None, log="setup"):
    """Filter command output into a private log; never echo a subprocess command/env."""
    redact = redactor(root)
    target = state_dir(root) / "logs" / f"{log}.log"
    with target.open("a", buffering=1) as out:
        proc = subprocess.Popen(args, cwd=cwd or root, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        try:
            for line in proc.stdout:
                out.write(redact(line))
            return proc.wait()
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()


def checked(root, args, cwd=None, env=None):
    if capture(root, args, cwd, env) != 0:
        raise DevError("준비 명령 실패. scripts/dev.sh logs setup으로 확인하세요 (비밀값 가림).")


def setup(root):
    import shutil
    uv = shutil.which("uv")
    python = require_tool("python3.11") if not uv else None
    for service in ("rag", "voice"):
        folder = root / f"{service}-service"
        venv = folder / ".venv"
        created = not venv.exists()
        if created:
            checked(root, [uv, "venv", "--python", "3.11", str(venv)] if uv else
                    [python, "-m", "venv", str(venv)])
        interpreter = py_for(root, service)
        version = subprocess.run([interpreter, "-c", "import sys; raise SystemExit(sys.version_info[:2] != (3,11))"])
        if version.returncode:
            raise DevError(f"{service} .venv는 Python 3.11이어야 합니다. 기존 환경은 보존했습니다.")
        names = ["requirements-data.txt", "requirements-rag.txt"] if service == "rag" else ["requirements.txt"]
        files = [folder / name for name in names] + [root / "common-py/pyproject.toml"]
        digest = hashlib.sha256(b"".join(p.read_bytes() for p in files) + interpreter.encode()).hexdigest()
        marker = state_dir(root) / "setup" / f"{service}.sha256"
        if not created and marker.is_file() and marker.read_text() == digest:
            check = [uv, "pip", "check", "--python", interpreter] if uv else [interpreter, "-m", "pip", "check"]
            if capture(root, check, folder) == 0:
                say(f"[SKIP] {service}: 설치 목록 변경 없음·의존성 확인 완료")
                continue
        args = [uv, "pip", "install", "--python", interpreter] if uv else [interpreter, "-m", "pip", "install"]
        for name in names:
            args.extend(["-r", name])
        args.extend(["-e", "../common-py[dev]"])
        checked(root, args, folder)
        checked(root, [uv, "pip", "check", "--python", interpreter] if uv else
                [interpreter, "-m", "pip", "check"], folder)
        marker.write_text(digest)
        say(f"[OK] {service}: Python 의존성 준비")
    require_tool("npm")
    frontend = root / "frontend"
    lock = frontend / "package-lock.json"
    inputs = [frontend / "package.json"] + ([lock] if lock.is_file() else [])
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in inputs)).hexdigest()
    marker = state_dir(root) / "setup/frontend.sha256"
    if not ((frontend / "node_modules").is_dir() and marker.is_file() and marker.read_text() == digest):
        checked(root, ["npm", "ci"] if lock.is_file() else ["npm", "install", "--package-lock=false"], frontend)
        marker.write_text(digest)
    else:
        say("[SKIP] frontend: 설치 목록 변경 없음")
    require_tool("java")
    checked(root, ["/bin/bash", "./gradlew", "--version", "--no-daemon"], root / "auth-server")
    say("[OK] setup 완료 (기존 .env·프론트 lockfile 보존)")


def init_env(root):
    path = root / ".env"
    with path.open("a+") as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        values = dotenv(path)
        if "JWT_SECRET" in values:
            if not values["JWT_SECRET"].strip():
                raise DevError("루트 .env의 JWT_SECRET이 비어 있습니다. 기존 값은 수정하지 않았습니다.")
            say("[SKIP] JWT_SECRET 존재: 기존 값 보존")
            return
        out.seek(0)
        existing = out.read()
        out.seek(0, 2)
        out.write(("\n" if existing and not existing.endswith("\n") else "") +
                  "JWT_SECRET=" + secrets.token_urlsafe(48) + "\n")
    say("[OK] 루트 .env에 JWT_SECRET 추가 (값 비출력)")


def docker_info():
    require_tool("docker")
    result = subprocess.run(["docker", "inspect", "referoom-mariadb"], capture_output=True, text=True)
    if result.returncode:
        raise DevError("referoom-mariadb 컨테이너가 없거나 Docker에 연결할 수 없습니다. 새 DB는 생성하지 않습니다.")
    info = json.loads(result.stdout)[0]
    bindings = info.get("NetworkSettings", {}).get("Ports", {}).get("3306/tcp") or []
    if not any(item.get("HostPort") == "53301" for item in bindings):
        raise DevError("referoom-mariadb의 3306→53301 포트 매핑을 확인하세요.")
    return info


def start(root, service):
    if service == "db":
        info = docker_info()
        if info["State"]["Running"]:
            say("[SKIP] db: 이미 실행 중 (기존 소유 기록 보존)")
            return
        if occupied(PORTS[service]):
            raise DevError("db 포트가 사용 중입니다. 기존 프로세스를 종료하지 않았습니다.")
        result = subprocess.run(["docker", "start", "referoom-mariadb"], capture_output=True)
        if result.returncode:
            raise DevError("DB 컨테이너 시작 실패 (상세 비출력).")
        record_path(root, service).write_text(json.dumps({"container": info["Id"], "root": str(root)}))
        say("[OK] db 시작 요청 완료")
        return
    record = read_record(root, service)
    if owned(root, record):
        say(f"[SKIP] {service}: 이 스크립트가 이미 실행 중")
        return
    if occupied(PORTS[service]):
        raise DevError(f"{service} 포트 {PORTS[service]} 사용 중. 기존 프로세스를 종료하지 않았습니다.")
    env = service_env(root, service)
    if service != "frontend" and not env.get("JWT_SECRET", "").strip():
        raise DevError("JWT_SECRET이 필요합니다. scripts/dev.sh init-env를 먼저 실행하세요.")
    if service == "auth" and not env.get("DB_PASSWORD"):
        raise DevError("DB_PASSWORD가 필요합니다. 실제 .env에 설정하세요.")
    commands(root, service)  # Validate prerequisites before launching a supervisor.
    record_path(root, service).unlink(missing_ok=True)
    proc = subprocess.Popen([sys.executable, str(root / "scripts/dev/manager.py"), "_supervise", service],
                            cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    CHILDREN[proc.pid] = proc
    for _ in range(50):
        record = read_record(root, service)
        if owned(root, record):
            say(f"[OK] {service} 프로세스 시작 (준비 상태는 status로 확인)")
            return
        if proc.poll() is not None:
            raise DevError(f"{service} 시작 실패. logs {service}로 확인하세요.")
        time.sleep(0.1)
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    raise DevError(f"{service} 시작 기록 확인 실패.")


def supervise(root, service):
    # Allow finally to reap the immediate child when down signals the process group.
    def terminate(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    path = record_path(root, service)
    cwd, args = commands(root, service)
    env = service_env(root, service)
    redact = redactor(root)
    log = root / ".run/logs" / f"{service}.log"
    record = {"pid": os.getpid(), "identity": identity(os.getpid()), "root": str(root)}
    if not record["identity"]:
        raise DevError("프로세스 소유 확인 불가: 서비스를 시작하지 않습니다.")
    with log.open("a", buffering=1) as out:
        proc = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record))
        tmp.replace(path)
        try:
            for line in proc.stdout:
                out.write(redact(line))
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
            if read_record(root, service) == record:
                path.unlink(missing_ok=True)


def stop(root, service):
    record = read_record(root, service)
    if service == "db":
        if not record:
            say("[SKIP] db: 이 스크립트가 시작한 DB 없음")
            return
        info = docker_info()
        if record.get("root") != str(root) or record.get("container") != info["Id"]:
            raise DevError("DB 소유 기록 불일치: 종료하지 않았습니다.")
        if subprocess.run(["docker", "stop", "referoom-mariadb"], capture_output=True).returncode:
            raise DevError("DB 종료 실패. 기록을 유지합니다.")
    elif owned(root, record):
        pid = record["pid"]
        os.killpg(pid, signal.SIGTERM)
        for _ in range(100):
            current = identity(pid)
            gone = not current or "<defunct>" in current
            if gone and not occupied(PORTS[service]):
                break
            time.sleep(0.1)
        else:
            raise DevError(f"{service} 종료/포트 반환 대기 초과. 기록 유지; 강제 종료하지 않았습니다.")
    else:
        say(f"[SKIP] {service}: 관리 프로세스 없음 (오래된 PID는 종료하지 않음)")
    if service != "db" and isinstance(record, dict):
        child = CHILDREN.pop(record.get("pid"), None)
        if child is not None:
            child.wait(timeout=5)
    record_path(root, service).unlink(missing_ok=True)
    say(f"[OK] {service} 종료 처리 완료")


def health(service):
    path = "/api/health" if service == "auth" else "/" if service == "frontend" else "/health"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{PORTS[service]}{path}", timeout=1) as response:
            payload = response.read(65536)
        if service == "frontend":
            return "HTTP 정상"
        data = json.loads(payload)
        if service == "auth":
            return "준비 완료" if data.get("ok") and data.get("db") == "up" else "DB 준비 필요"
        if service == "voice":
            return "준비 완료" if data.get("whisper") == "ready" else "시작 중/모델 준비 필요"
        return "준비 완료" if data.get("embedder") is True else "HTTP 정상/모델 상태 확인 필요"
    except urllib.error.HTTPError as exc:
        return "시작 중/모델 준비 필요 (503)" if exc.code == 503 else f"HTTP {exc.code}"
    except (OSError, ValueError):
        return "헬스 응답 없음"


def status(root):
    for service in SERVICES:
        if service == "db":
            try:
                info = docker_info()
                say("db: " + ("실행 중" if info["State"]["Running"] else "중지"))
            except DevError as exc:
                say(f"db: {exc}")
            continue
        record = read_record(root, service)
        state = "관리 프로세스 실행 중" if owned(root, record) else "외부 포트 사용 중" if occupied(PORTS[service]) else "중지"
        say(f"{service}: {state}; {health(service)}")


def test(root):
    results = []
    offline = str(root / "scripts/dev/offline")
    for label, cwd, args in [
        ("common-py", root / "common-py", ["rag-python", "-m", "pytest", "-q", "tests"]),
        ("rag", root / "rag-service", ["rag-python", "-m", "pytest", "-q", "tests"]),
        ("voice", root / "voice-service", ["voice-python", "-m", "pytest", "-q", "tests"]),
        ("frontend", root / "frontend", ["npm", "test"]),
        ("auth", root / "auth-server", ["/bin/bash", "./gradlew", ":app:build", "--no-daemon"]),
    ]:
        env = os.environ.copy()
        env.update(OPENAI_API_KEY="offline-test-key", LLM_API_KEY="offline-test-key",
                   PYTHONPATH=offline + os.pathsep + env.get("PYTHONPATH", ""))
        try:
            if args[0].endswith("-python"):
                args[0] = py_for(root, args[0].split("-")[0])
            code = capture(root, args, cwd, env, log=f"test-{label}")
        except (OSError, DevError):
            code = 1
        results.append(code)
        say(f"[{'PASS' if code == 0 else 'FAIL'}] {label}")
    return int(any(results))


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Referoom B3 개발 환경 관리")
    parser.add_argument("command", choices=("setup", "init-env", "up", "down", "status", "logs", "restart", "test", "_supervise"))
    parser.add_argument("services", nargs="*")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    command, names = args.command, args.services
    if command == "logs":
        if len(names) != 1 or names[0] not in (*SERVICES, "setup", *(f"test-{s}" for s in ("common-py", "rag", "voice", "frontend", "auth"))):
            raise DevError("logs에는 허용된 서비스 또는 setup/test-서비스 이름 하나가 필요합니다.")
        path = root / ".run/logs" / f"{names[0]}.log"
        if not path.is_file():
            raise DevError("아직 로그가 없습니다.")
        return subprocess.call(["tail", "-n", "50", "-f", str(path)])
    if any(name not in SERVICES for name in names):
        raise DevError("서비스는 db/auth/rag/voice/frontend만 사용할 수 있습니다.")
    if command in ("setup", "init-env", "status", "test") and names:
        raise DevError("이 명령에는 서비스 인자를 사용할 수 없습니다.")
    if command in ("restart", "_supervise") and len(names) != 1:
        raise DevError("서비스 하나를 지정하세요.")
    if command == "_supervise":
        supervise(root, names[0])
        return 0
    if command == "status":
        status(root)
        return 0
    with locked(root):
        if command == "setup": setup(root)
        elif command == "init-env": init_env(root)
        elif command == "test": return test(root)
        elif command == "restart":
            stop(root, names[0])
            start(root, names[0])
        else:
            selected = [s for s in SERVICES if not names or s in names]
            failures = []
            for service in selected if command == "up" else reversed(selected):
                try:
                    (start if command == "up" else stop)(root, service)
                except DevError as exc:
                    say(f"[FAIL] {service}: {exc}")
                    failures.append(service)
                    if command == "up":
                        break
            if failures:
                raise DevError("일부 작업 실패. 이미 실행한 서비스는 유지되며 status/down으로 관리하세요.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DevError as exc:
        say(f"[ERROR] {exc}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        say("[STOP] 사용자 중단. status로 실행 상태를 확인하세요.")
        raise SystemExit(130)
    except Exception:
        say("[ERROR] 실행 실패. 도구·권한·환경 설정을 확인하세요 (상세·비밀값 비출력).")
        raise SystemExit(1)
