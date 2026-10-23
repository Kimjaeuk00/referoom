package workplace.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import workplace.dto.res.MeResDTO;
import workplace.security.CustomPrincipal;
import workplace.service.UserService;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "사용자", description = "사용자 정보 API")
public class UserController {

    private final UserService userService;

    @GetMapping("/me")
    @Operation(summary = "내 정보 조회")
    @SecurityRequirement(name = "bearerAuth")
    public MeResDTO getMe(
        @Parameter(hidden = true)
        @AuthenticationPrincipal CustomPrincipal principal
    ) {
        return userService.getMe(principal.userId());
    }
}
