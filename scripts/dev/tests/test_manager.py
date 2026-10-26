"""Offline lifecycle tests; all files/processes are confined to temporary projects."""
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

MANAGER = Path(__file__).resolve().parents[1] / "manager.py"
spec = importlib.util.spec_from_file_location("dev_manager", MANAGER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="referoom dev test ")
        self.root = Path(self.temp.name).resolve()
        (self.root / "scripts/dev").mkdir(parents=True)
        shutil.copy2(MANAGER, self.root / "scripts/dev/manager.py")
        m.state_dir(self.root)
        safe_env = {key:value for key,value in os.environ.items() if not any(word in key.upper() for word in ("SECRET", "PASSWORD", "API_KEY", "TOKEN"))}
        safe_env.update(JWT_SECRET="test-jwt-secret", DB_PASSWORD="test-db-password")
        self.env = patch.dict(os.environ, safe_env, clear=True)
        self.env.start()
        self.old_umask = os.umask(0o077)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        for service in ("voice", "rag"):
            try:
                m.stop(self.root, service)
            except m.DevError:
                pass
        self.env.stop()
        self.temp.cleanup()
        os.umask(self.old_umask)
        self.output.__exit__(None,None,None)

    def test_dotenv_literal_and_comments(self):
        path = self.root / ".env"
        path.write_text('A="value # literal"\nB=hello # comment\nexport C=world\nD=$(touch SHOULD_NOT_EXIST)\n')
        values = m.dotenv(path)
        self.assertEqual(values["A"], "value # literal")
        self.assertEqual(values["B"], "hello")
        self.assertEqual(values["D"], "$(touch SHOULD_NOT_EXIST)")
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())

    def test_dotenv_rejects_invalid_without_values(self):
        path = self.root / ".env"
        path.write_text('invalid secret-value')
        with self.assertRaises(m.DevError) as error:
            m.dotenv(path)
        self.assertNotIn("secret-value", str(error.exception))

    def test_init_env_preserves_and_is_idempotent(self):
        path = self.root / ".env"
        path.write_text('EXISTING=keep')
        m.init_env(self.root)
        first = path.read_bytes()
        m.init_env(self.root)
        self.assertEqual(first, path.read_bytes())
        self.assertTrue(first.startswith(b"EXISTING=keep\n"))
        self.assertEqual(first.count(b"JWT_SECRET="), 1)
        self.assertTrue(m.dotenv(path)["JWT_SECRET"])

    def test_init_env_blank_key_is_not_overwritten(self):
        path = self.root / ".env"
        path.write_text('JWT_SECRET=\n')
        with self.assertRaises(m.DevError):
            m.init_env(self.root)
        self.assertEqual(path.read_text(), 'JWT_SECRET=\n')

    def test_shared_jwt_overrides_service_and_preserves_local_key(self):
        (self.root / "voice-service").mkdir()
        (self.root / "voice-service/.env").write_text('JWT_SECRET=wrong\nOPENAI_API_KEY=local-secret\n')
        env = m.service_env(self.root, "voice")
        self.assertEqual(env["JWT_SECRET"], "test-jwt-secret")
        self.assertEqual(env["OPENAI_API_KEY"], "local-secret")

    def test_rag_uses_the_real_local_index_unless_told_otherwise(self):
        (self.root / "rag-service").mkdir()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RAG_STORE", None)
            self.assertEqual(m.service_env(self.root, "rag")["RAG_STORE"], "local")
            (self.root / "rag-service/.env").write_text("RAG_STORE=stub\n")
            self.assertEqual(m.service_env(self.root, "rag")["RAG_STORE"], "stub")  # 직접 정한 값이 우선
            self.assertNotIn("RAG_STORE", m.service_env(self.root, "voice"))  # 다른 서비스에는 넣지 않는다

    def test_redacts_secrets_and_bearer(self):
        (self.root / ".env").write_text('OPENAI_API_KEY=test-api-secret\n')
        text = m.redactor(self.root)('test-api-secret test-jwt-secret Bearer abc.def.ghi')
        for value in ("test-api-secret", "test-jwt-secret", "abc.def.ghi"):
            self.assertNotIn(value, text)

    def test_foreign_pid_is_never_killed(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        try:
            m.record_path(self.root, "voice").write_text(json.dumps({"pid": proc.pid, "root": str(self.root), "identity": "stale identity"}))
            m.stop(self.root, "voice")
            self.assertIsNone(proc.poll())
        finally:
            proc.terminate()
            proc.wait()

    def test_busy_port_is_preserved(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            with patch.dict(m.PORTS, voice=sock.getsockname()[1]):
                with self.assertRaisesRegex(m.DevError, "포트"):
                    m.start(self.root, "voice")
            self.assertGreater(sock.fileno(), 0)

    def test_process_lifecycle_restart_and_private_redacted_log(self):
        folder = self.root / "voice-service/.venv/bin"
        folder.mkdir(parents=True)
        worker = folder / "python"
        worker.write_text('#!' + sys.executable + '\nimport os,time\nprint(os.environ["JWT_SECRET"],flush=True)\nwhile True: time.sleep(1)\n')
        worker.chmod(0o755)
        for _ in range(2):
            m.start(self.root, "voice")
            record = m.read_record(self.root, "voice")
            self.assertTrue(m.owned(self.root, record))
            m.start(self.root, "voice")
            self.assertEqual(m.read_record(self.root, "voice"), record)
            for attempt in range(30):
                log = self.root / ".run/logs/voice.log"
                if log.exists() and '[REDACTED]' in log.read_text():
                    break
                time.sleep(.05)
            self.assertIn('[REDACTED]', log.read_text())
            self.assertEqual(log.stat().st_mode & 0o077, 0)
            self.assertNotIn('test-jwt-secret', log.read_text())
            m.stop(self.root, "voice")
            m.stop(self.root, "voice")
            self.assertFalse(m.record_path(self.root, "voice").exists())

    def test_stop_waits_until_listening_port_is_released(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        folder = self.root / "voice-service/.venv/bin"
        folder.mkdir(parents=True)
        worker = folder / "python"
        worker.write_text('#!' + sys.executable + '\nimport os\nfrom http.server import HTTPServer,BaseHTTPRequestHandler\nHTTPServer(("127.0.0.1",int(os.environ["TEST_HTTP_PORT"])),BaseHTTPRequestHandler).serve_forever()\n')
        worker.chmod(0o755)
        with patch.dict(os.environ, TEST_HTTP_PORT=str(port)), patch.dict(m.PORTS, voice=port):
            m.start(self.root, "voice")
            for attempt in range(50):
                if m.occupied(port):
                    break
                time.sleep(.05)
            self.assertTrue(m.occupied(port))
            m.stop(self.root, "voice")
            self.assertFalse(m.occupied(port))
            self.assertFalse(m.record_path(self.root,"voice").exists())

    def test_external_db_not_stopped(self):
        with patch.object(m, 'docker_info', return_value={"Id":"one","State":{"Running":True}}), patch.object(m.subprocess, 'run') as run:
            m.start(self.root, "db")
            m.stop(self.root, "db")
            run.assert_not_called()

    def test_owned_db_identity_and_stop(self):
        path = m.record_path(self.root, "db")
        path.write_text(json.dumps({"container":"one","root":str(self.root)}))
        with patch.object(m, 'docker_info', return_value={"Id":"two"}):
            with self.assertRaises(m.DevError): m.stop(self.root, "db")
        self.assertTrue(path.exists())
        with patch.object(m, 'docker_info', return_value={"Id":"one"}), patch.object(m.subprocess, 'run') as run:
            run.return_value.returncode = 0
            m.stop(self.root, "db")
            run.assert_called_once()
        self.assertFalse(path.exists())

    def test_setup_installs_only_when_inputs_change(self):
        for service, names in [('rag',['requirements-data.txt','requirements-rag.txt']), ('voice',['requirements.txt'])]:
            folder=self.root / f'{service}-service'
            (folder/'.venv/bin').mkdir(parents=True)
            interpreter=folder/'.venv/bin/python'
            interpreter.write_text('#!/bin/sh\nexit 0\n')
            interpreter.chmod(0o755)
            for name in names: (folder/name).write_text('example\n')
        (self.root/'common-py').mkdir()
        (self.root/'common-py/pyproject.toml').write_text('example')
        (self.root/'frontend/node_modules').mkdir(parents=True)
        (self.root/'frontend/package.json').write_text('{}')
        lock=self.root/'frontend/package-lock.json'
        lock.write_text('{}')
        calls=[]
        def checked(root,args,cwd=None,env=None):
            calls.append(args)
            if len(args)>1 and args[1]=="venv":
                target=Path(args[-1])/"bin/python"
                target.parent.mkdir(parents=True)
                target.write_text("#!/bin/sh\nexit 0\n")
                target.chmod(0o755)
        with patch.object(m,'checked',side_effect=checked), patch.object(m,'capture',return_value=0), patch.object(m,'require_tool',return_value='tool'), patch('shutil.which',return_value='uv'):
            m.setup(self.root)
            count=len(calls)
            m.setup(self.root)
            self.assertEqual(len(calls),count+1) # Gradle version only.
            (self.root/'voice-service/requirements.txt').write_text('changed')
            m.setup(self.root)
            self.assertEqual(len(calls),count+4) # Voice install/check + Gradle.
            shutil.rmtree(self.root/"voice-service/.venv")
            m.setup(self.root)
            self.assertEqual(len(calls),count+8) # New venv must reinstall, even with old marker.
        self.assertIn(['npm','ci'],calls)
        self.assertEqual(lock.read_text(),'{}')

    def test_offline_python_guard_blocks_connections(self):
        offline=MANAGER.parent/'offline'
        env={**os.environ,'PYTHONPATH':str(offline)}
        result=subprocess.run([sys.executable,'-c','import socket; socket.create_connection(("example.com",443))'],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('network disabled',result.stderr)

    def test_missing_environments_still_report_all_suites(self):
        with patch.object(m,'capture',return_value=1) as capture:
            self.assertEqual(m.test(self.root),1)
            self.assertEqual(capture.call_count,2) # frontend + auth, despite absent Python envs.


if __name__ == '__main__':
    unittest.main()
