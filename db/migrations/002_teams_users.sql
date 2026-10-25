-- 새 DB 최초 초기화용: 001_users.sql 실행 후 적용한다.
-- 기존 teams 테이블이나 fk_users_team 외래키가 있는 DB에는 다시 실행하지 않는다.

CREATE TABLE teams (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    name VARCHAR(100) NOT NULL,

    invite_code VARCHAR(16) NOT NULL,

    created_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    CONSTRAINT uk_teams_invite_code
        UNIQUE (invite_code)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;


ALTER TABLE users
    ADD CONSTRAINT fk_users_team
    FOREIGN KEY (team_id)
    REFERENCES teams (id);
