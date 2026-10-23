package workplace.security;

import java.io.IOException;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
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

        String authorization = request.getHeader(
            HttpHeaders.AUTHORIZATION
        );

        if (authorization == null) {
            filterChain.doFilter(request, response);
            return;
        }

        try {
            String[] parts = authorization.strip().split("\\s+", 2);

            if (parts.length != 2
                || !"Bearer".equalsIgnoreCase(parts[0])
                || parts[1].isBlank()) {
                throw new ApiException(ErrorCode.UNAUTHORIZED);
            }

            CustomPrincipal principal = jwtTokenProvider.verifyToken(
                parts[1]
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
}
