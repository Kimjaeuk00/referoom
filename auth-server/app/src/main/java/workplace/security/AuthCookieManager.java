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

    public void clearAuthCookies(
        HttpServletResponse response,
        boolean secure
    ) {
        expireCookie(response, "ACCESS_TOKEN", true, secure);
        expireCookie(response, "SESSION_ID", true, secure);
        expireCookie(response, "APP_AUTH", false, secure);
    }

    private void expireCookie(
        HttpServletResponse response,
        String name,
        boolean httpOnly,
        boolean secure
    ) {
        ResponseCookie cookie = ResponseCookie
            .from(name, "")
            .httpOnly(httpOnly)
            .secure(secure)
            .sameSite("Lax")
            .path("/")
            .maxAge(0)
            .build();

        response.addHeader(
            HttpHeaders.SET_COOKIE,
            cookie.toString()
        );
    }
}
