package workplace.exception;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import workplace.dto.res.ErrorResDTO;
import workplace.enums.ErrorCode;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    // 서비스에서 의도적으로 발생시킨 API 예외
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResDTO> handleApiException(
        ApiException exception
    ) {
        return createErrorResponse(exception.getErrorCode());
    }

    // @Valid 요청 DTO 검증 실패
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResDTO> handleValidationException() {
        return createErrorResponse(ErrorCode.VALIDATION_ERROR);
    }

    // JSON 파싱 실패 또는 요청 파라미터 타입 불일치
    @ExceptionHandler({
        HttpMessageNotReadableException.class,
        MethodArgumentTypeMismatchException.class
    })
    public ResponseEntity<ErrorResDTO> handleBadRequestException() {
        return createErrorResponse(ErrorCode.BAD_REQUEST);
    }

    // 그 외 예외
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResDTO> handleException(
        Exception exception
    ) {
        // Spring MVC의 404·405·415 등은 원래 HTTP 상태를 유지
        if (exception instanceof ErrorResponse frameworkError) {
            HttpStatus status = HttpStatus.resolve(
                frameworkError.getStatusCode().value()
            );

            String code = status != null
                ? status.name()
                : "HTTP_" + frameworkError.getStatusCode().value();

            String message = status != null
                ? status.getReasonPhrase()
                : "요청을 처리할 수 없습니다.";

            return ResponseEntity
                .status(frameworkError.getStatusCode())
                .headers(frameworkError.getHeaders())
                .body(new ErrorResDTO(false, message, code));
        }

        // 예외 원문·요청 데이터 대신 예외 종류만 기록
        log.error(
            "예상하지 못한 서버 오류: type={}",
            exception.getClass().getSimpleName()
        );

        return createErrorResponse(ErrorCode.INTERNAL_SERVER_ERROR);
    }

    private ResponseEntity<ErrorResDTO> createErrorResponse(
        ErrorCode errorCode
    ) {
        return ResponseEntity
            .status(errorCode.getStatus())
            .body(
                new ErrorResDTO(
                    false,
                    errorCode.getMessage(),
                    errorCode.getCode()
                )
            );
    }
}