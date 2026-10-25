-- v0.2: 사용자 수준 컬럼은 없다(JWT에도 level claim이 없다).
-- 새 DB 최초 초기화용: 001_users.sql → 002_teams_users.sql 순서로 실행한다.
-- 기존 JPA 테이블이 있는 DB에는 다시 실행하지 않는다.
-- teams 생성 후 002에서 team_id 외래키를 연결한다.

CREATE TABLE users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    username VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NULL,
    password VARCHAR(255) NOT NULL,

    team_id BIGINT UNSIGNED NULL,

    role ENUM('member', 'team_admin')
        NOT NULL DEFAULT 'member',

    view_pref ENUM('dev', 'rnd') NULL,

    created_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    CONSTRAINT uk_users_username
        UNIQUE (username),

    INDEX idx_users_team (team_id)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
