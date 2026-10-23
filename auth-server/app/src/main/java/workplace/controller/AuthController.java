package workplace.controller;

import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import workplace.dto.req.LoginReqDTO;
import workplace.dto.req.SignupReqDTO;
import workplace.dto.res.LoginResDTO;
import workplace.dto.res.SignupResDTO;
import workplace.security.AuthCookieManager;
import workplace.service.AuthService;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Auth", description = "회원가입 및 로그인")
public class AuthController {

    private final AuthService authService;
    private final AuthCookieManager authCookieManager;

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
}