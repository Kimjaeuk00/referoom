package workplace.controller;

import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.bind.annotation.*;
import workplace.converter.UserConverter;
import workplace.dto.req.LoginReqDTO;
import workplace.dto.req.SignupReqDTO;
import workplace.dto.res.AuthCheckResDTO;
import workplace.dto.res.LoginResDTO;
import workplace.dto.res.SignupResDTO;
import workplace.dto.res.SuccessResDTO;
import workplace.security.AuthCookieManager;
import workplace.security.CustomPrincipal;
import workplace.service.AuthService;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Auth", description = "회원가입 및 로그인")
public class AuthController {

    private final AuthService authService;
    private final AuthCookieManager authCookieManager;
    private final SecurityContextLogoutHandler logoutHandler =
        new SecurityContextLogoutHandler();

    @PostMapping(
        value = "/signup",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "회원가입")
    public SignupResDTO signup(
        @Valid @RequestBody SignupReqDTO request
    ) {
        return authService.signup(request);
    }

    @Hidden
    @PostMapping(
        value = "/signup",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    @ResponseStatus(HttpStatus.CREATED)
    public SignupResDTO signupForm(
        @Valid @ModelAttribute SignupReqDTO request
    ) {
        return authService.signup(request);
    }

    @PostMapping(
        value = "/login",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(summary = "로그인")
    public LoginResDTO login(
        @Valid @RequestBody LoginReqDTO request,
        HttpServletRequest servletRequest,
        HttpServletResponse servletResponse
    ) {
        LoginResDTO result = authService.login(request);

        authCookieManager.setAccessTokenCookie(
            servletResponse,
            result.getAccessToken(),
            result.getExpiresIn(),
            servletRequest.isSecure()
        );

        return result;
    }

    @Hidden
    @PostMapping(
        value = "/login",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public LoginResDTO loginForm(
        @Valid @ModelAttribute LoginReqDTO request,
        HttpServletRequest servletRequest,
        HttpServletResponse servletResponse
    ) {
        return login(
            request,
            servletRequest,
            servletResponse
        );
    }

    @GetMapping("/auth/check")
    @Operation(
        summary = "인증 상태 확인",
        description = "Bearer 헤더를 우선 검증하고, 헤더가 없으면 ACCESS_TOKEN 쿠키를 검증합니다."
    )
    @SecurityRequirements({
        @SecurityRequirement(name = "bearerAuth"),
        @SecurityRequirement(name = "cookieAuth")
    })
    public AuthCheckResDTO checkAuth(
        @Parameter(hidden = true)
        @AuthenticationPrincipal CustomPrincipal principal
    ) {
        return authService.checkAuth(principal.userId());
    }

    @PostMapping("/logout")
    @Operation(
        summary = "로그아웃",
        description = "인증 상태와 관계없이 인증 쿠키를 삭제하고 현재 보안 컨텍스트를 정리합니다."
    )
    public SuccessResDTO logout(
        @Parameter(hidden = true)
        Authentication authentication,
        HttpServletRequest servletRequest,
        HttpServletResponse servletResponse
    ) {
        logoutHandler.logout(
            servletRequest,
            servletResponse,
            authentication
        );

        authCookieManager.clearAuthCookies(
            servletResponse,
            servletRequest.isSecure()
        );

        return UserConverter.toSuccessResDTO();
    }
}
