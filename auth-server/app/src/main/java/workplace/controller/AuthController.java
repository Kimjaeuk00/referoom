package workplace.controller;

import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import workplace.dto.req.SignupReqDTO;
import workplace.dto.res.SignupResDTO;
import workplace.service.AuthService;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Auth", description = "회원가입 및 로그인")
public class AuthController {

    private final AuthService authService;

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
}