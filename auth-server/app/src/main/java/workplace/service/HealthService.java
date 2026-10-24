package workplace.service;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import workplace.dto.res.HealthResDTO;
import workplace.enums.ErrorCode;
import workplace.exception.ApiException;

@Slf4j
@Service
@RequiredArgsConstructor
public class HealthService {

    private final EntityManager entityManager;

    public HealthResDTO checkHealth() {
        try {
            Object result = entityManager
                .createNativeQuery("SELECT 1")
                .getSingleResult();

            if (result instanceof Number number
                    && number.intValue() == 1) {
                return new HealthResDTO(true, "up");
            }

            throw new ApiException(ErrorCode.NOT_READY);

        } catch (PersistenceException exception) {
            log.warn("DB 상태 확인 실패");

            throw new ApiException(
                ErrorCode.NOT_READY,
                exception
            );
        }
    }
}