package workplace.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import workplace.dto.res.HealthResDTO;
import workplace.service.HealthService;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Health", description = "서버 및 DB 상태 확인")
public class HealthController {

    private final HealthService healthService;

    @GetMapping("/health")
    @Operation(summary = "서버 및 DB 연결 상태 확인")
    public HealthResDTO checkHealth() {
        return healthService.checkHealth();
    }
}