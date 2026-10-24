-- 개발·데모 환경 전용: 001_users.sql·002_teams_users.sql 적용 후 실행한다.
-- 공통 로그인 비밀번호: Demo-pass-1234!
-- BCrypt cost 12로 생성하고 jBCrypt로 비교 확인한 개발용 비밀번호 해시다.
-- 동일한 초대 코드·아이디가 있으면 기존 데이터를 덮어쓰지 않는다.
-- 초대 코드 재발급 후 재실행하면 고정 코드의 팀이 새로 생길 수 있다.

START TRANSACTION;

SET @demo_password_hash =
    '$2a$12$twtMTZfqL5lTYOJWvwQdEOXzQNwLFT79T10BDizCMEVVUpNhmsYZK';


-- 1. 개발용 팀 생성
-- 같은 초대 코드가 있으면 기존 팀을 사용한다.

INSERT INTO teams (
    name,
    team_type,
    invite_code
)
SELECT
    '레퍼룸 개발 데모팀',
    'dev',
    'RFDEV234'
WHERE NOT EXISTS (
    SELECT 1
    FROM teams
    WHERE invite_code = 'RFDEV234'
);


-- 자동 생성된 팀 ID를 조회한다.

SET @demo_team_id = (
    SELECT id
    FROM teams
    WHERE invite_code = 'RFDEV234'
);


-- 2. 팀 관리자

INSERT INTO users (
    username,
    display_name,
    password,
    team_id,
    role,
    skill_level,
    view_pref
)
SELECT
    'demo_admin',
    '데모 관리자',
    @demo_password_hash,
    @demo_team_id,
    'team_admin',
    'L2',
    NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE username = 'demo_admin'
);


-- 3. 일반 팀원

INSERT INTO users (
    username,
    display_name,
    password,
    team_id,
    role,
    skill_level,
    view_pref
)
SELECT
    'demo_member',
    '데모 팀원',
    @demo_password_hash,
    @demo_team_id,
    'member',
    'L1',
    NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE username = 'demo_member'
);


-- 4. 팀 미가입 사용자

INSERT INTO users (
    username,
    display_name,
    password,
    team_id,
    role,
    skill_level,
    view_pref
)
SELECT
    'demo_solo',
    '데모 미가입 사용자',
    @demo_password_hash,
    NULL,
    'member',
    'L2',
    NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE username = 'demo_solo'
);

COMMIT;
