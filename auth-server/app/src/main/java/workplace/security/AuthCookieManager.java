package workplace.security;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

@Component
public class AuthCookieManager {

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