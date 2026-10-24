package workplace.enums;

import lombok.AllArgsConstructor;
import lombok.Getter;
import org.springframework.http.HttpStatus;

@Getter
@AllArgsConstructor
public enum ErrorCode {

    // 요청 오류
    BAD_REQUEST(
        HttpStatus.BAD_REQUEST,
        "BAD_REQUEST",
        "요청 형식이 올바르지 않습니다."
    ),
    VALIDATION_ERROR(
        HttpStatus.UNPROCESSABLE_CONTENT,
        "VALIDATION_ERROR",
        "입력값을 확인해 주세요."
    ),

    // 인증 오류
    INVALID_CREDENTIALS(
        HttpStatus.UNAUTHORIZED,
        "INVALID_CREDENTIALS",
        "invalid credentials"
    ),
    UNAUTHORIZED(
        HttpStatus.UNAUTHORIZED,
        "UNAUTHORIZED",
        "인증이 필요합니다."
    ),
    TOKEN_EXPIRED(
        HttpStatus.UNAUTHORIZED,
        "TOKEN_EXPIRED",
        "인증이 만료되었습니다. 다시 로그인해 주세요."
    ),

    // 권한 오류
    NO_TEAM(
        HttpStatus.FORBIDDEN,
        "NO_TEAM",
        "팀 가입이 필요합니다."
    ),
    FORBIDDEN(
        HttpStatus.FORBIDDEN,
        "FORBIDDEN",
        "접근 권한이 없습니다."
    ),

    // 회원·팀 오류
    CONFLICT(
        HttpStatus.CONFLICT,
        "CONFLICT",
        "이미 사용 중인 아이디입니다."
    ),
    TEAM_NOT_FOUND(
        HttpStatus.NOT_FOUND,
        "TEAM_NOT_FOUND",
        "해당하는 팀을 찾을 수 없습니다."
    ),
    ALREADY_IN_TEAM(
        HttpStatus.CONFLICT,
        "ALREADY_IN_TEAM",
        "이미 팀에 가입되어 있습니다."
    ),

    // 서버 오류
    NOT_READY(
        HttpStatus.SERVICE_UNAVAILABLE,
        "NOT_READY",
        "인증 서비스를 준비 중입니다."
    ),
    INTERNAL_SERVER_ERROR(
        HttpStatus.INTERNAL_SERVER_ERROR,
        "INTERNAL_SERVER_ERROR",
        "서버 내부 오류가 발생했습니다."
    );

    private final HttpStatus status;
    private final String code;
    private final String message;
}