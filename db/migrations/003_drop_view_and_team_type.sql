-- 관점(users.view_pref)과 팀 유형(teams.team_type) 컬럼 삭제.
-- 설계: docs/v0.3/시나리오_레퍼룸_v0.3.md 결정 1. 인증서버가 두 컬럼을 더 이상 읽거나 쓰지 않는 버전으로 바뀐 뒤에 적용한다.
-- 새 DB(001·002를 이미 고친 상태로 초기화한 DB)에서는 컬럼이 없으므로 IF EXISTS로 건너뛴다(여러 번 실행해도 안전).
-- 되돌리려면 아래 두 줄을 실행한다. 삭제된 값은 복구되지 않는다(팀 유형은 대부분 'dev', 관점은 NULL이었다).
--   ALTER TABLE users ADD COLUMN view_pref ENUM('dev', 'rnd') NULL AFTER role;
--   ALTER TABLE teams ADD COLUMN team_type ENUM('dev', 'rnd') NOT NULL DEFAULT 'dev' AFTER name;

ALTER TABLE users DROP COLUMN IF EXISTS view_pref;
ALTER TABLE teams DROP COLUMN IF EXISTS team_type;
