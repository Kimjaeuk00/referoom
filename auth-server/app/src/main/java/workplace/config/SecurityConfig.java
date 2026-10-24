package workplace.config;

import jakarta.servlet.DispatcherType;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.servlet.HandlerExceptionResolver;
import workplace.enums.ErrorCode;
import workplace.exception.ApiException;
import workplace.security.JwtAuthenticationFilter;
import workplace.security.JwtTokenProvider;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        JwtTokenProvider jwtTokenProvider,
        @Qualifier("handlerExceptionResolver")
        HandlerExceptionResolver exceptionResolver
    ) throws Exception {

        JwtAuthenticationFilter jwtAuthenticationFilter =
            new JwtAuthenticationFilter(
                jwtTokenProvider,
                exceptionResolver
            );

        http
            .csrf(AbstractHttpConfigurer::disable)
            .cors(withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .requestCache(AbstractHttpConfigurer::disable)

            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )

            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR
                ).permitAll()

                .requestMatchers(
                    HttpMethod.OPTIONS,
                    "/**"
                ).permitAll()

                .requestMatchers(
                    "/api/signup",
                    "/api/login",
                    "/api/logout",
                    "/api/health",
                    "/swagger-ui.html",
                    "/swagger-ui/**",
                    "/v3/api-docs",
                    "/v3/api-docs/**",
                    "/v3/api-docs.yaml"
                ).permitAll()

                .anyRequest().authenticated()
            )

            .exceptionHandling(exception -> exception
                .authenticationEntryPoint(
                    (request, response, authException) -> {
                        response.setHeader(
                            HttpHeaders.WWW_AUTHENTICATE,
                            "Bearer"
                        );

                        exceptionResolver.resolveException(
                            request,
                            response,
                            null,
                            new ApiException(
                                ErrorCode.UNAUTHORIZED
                            )
                        );
                    }
                )

                .accessDeniedHandler(
                    (request, response, accessDeniedException) ->
                        exceptionResolver.resolveException(
                            request,
                            response,
                            null,
                            new ApiException(
                                ErrorCode.FORBIDDEN
                            )
                        )
                )
            )

            .addFilterBefore(
                jwtAuthenticationFilter,
                UsernamePasswordAuthenticationFilter.class
            );

        return http.build();
    }
}
