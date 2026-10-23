package workplace.security;

import java.io.IOException;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerExceptionResolver;
import workplace.enums.ErrorCode;
import workplace.exception.ApiException;

@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String AUTH_CHECK_PATH = "/api/auth/check";
    private static final String ACCESS_TOKEN_COOKIE = "ACCESS_TOKEN";

    private static final Set<String> PUBLIC_API_PATHS = Set.of(
        "/api/signup",
        "/api/login",
        "/api/health"
    );

    private final JwtTokenProvider jwtTokenProvider;
    private final HandlerExceptionResolver exceptionResolver;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();

        return "OPTIONS".equalsIgnoreCase(request.getMethod())
            || !path.startsWith("/api/")
            || PUBLIC_API_PATHS.contains(path);
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {

        try {
            String accessToken = resolveToken(request);

            if (accessToken != null) {
                authenticate(accessToken);
            }
        } catch (ApiException exception) {
            SecurityContextHolder.clearContext();

            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer"
            );

            exceptionResolver.resolveException(
                request,
                response,
                null,
                exception
            );

            return;
        }

        filterChain.doFilter(request, response);
    }

    private String resolveToken(HttpServletRequest request) {
        String authorization = request.getHeader(
            HttpHeaders.AUTHORIZATION
        );

        // Authorization 헤더가 있으면 반드시 해당 값을 사용
        if (authorization != null) {
            String[] parts = authorization.strip().split("\\s+", 2);

            if (parts.length != 2
                || !"Bearer".equalsIgnoreCase(parts[0])
                || parts[1].isBlank()) {
                throw new ApiException(
                    ErrorCode.UNAUTHORIZED
                );
            }

            return parts[1];
        }

        // 쿠키 인증은 GET /api/auth/check에만 허용
        if (!"GET".equals(request.getMethod())
            || !AUTH_CHECK_PATH.equals(request.getServletPath())) {
            return null;
        }

        Cookie[] cookies = request.getCookies();

        if (cookies == null) {
            return null;
        }

        for (Cookie cookie : cookies) {
            if (ACCESS_TOKEN_COOKIE.equals(cookie.getName())) {
                String value = cookie.getValue();

                if (value == null || value.isBlank()) {
                    throw new ApiException(
                        ErrorCode.UNAUTHORIZED
                    );
                }

                return value;
            }
        }

        return null;
    }

    private void authenticate(String accessToken) {
        CustomPrincipal principal = jwtTokenProvider.verifyToken(
            accessToken
        );

        SimpleGrantedAuthority authority =
            new SimpleGrantedAuthority(
                "ROLE_" + principal.role()
                    .name()
                    .toUpperCase(Locale.ROOT)
            );

        var authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                principal,
                null,
                List.of(authority)
            );

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);

        SecurityContextHolder.setContext(context);
    }
}
