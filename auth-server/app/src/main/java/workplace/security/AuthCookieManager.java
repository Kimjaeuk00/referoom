package workplace.security;

import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;
import workplace.config.JwtProperties;

@Component
@RequiredArgsConstructor
public class AuthCookieManager {

    private final JwtProperties jwtProperties;

    public void setAccessTokenCookie(
        HttpServletResponse response,
        String accessToken,
        boolean secure
    ) {
        setAccessTokenCookie(
            response,
            accessToken,
            jwtProperties.getExpirationSeconds(),
            secure
        );
    }

    public void setAccessTokenCookie(
        HttpServletResponse response,
        String accessToken,
        long expiresIn,
        boolean secure
    ) {
        ResponseCookie cookie = ResponseCookie
            .from("ACCESS_TOKEN", accessToken)
            .httpOnly(true)
            .secure(secure)
            .sameSite("Lax")
            .path("/")
            .maxAge(expiresIn)
            .build();

        response.addHeader(
            HttpHeaders.SET_COOKIE,
            cookie.toString()
        );
    }
}
