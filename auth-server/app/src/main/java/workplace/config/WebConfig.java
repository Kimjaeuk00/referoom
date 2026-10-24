package workplace.config;

import java.util.Arrays;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class WebConfig {

    @Bean
    public UrlBasedCorsConfigurationSource corsConfigurationSource(
        @Value("${app.cors-allowed-origins}")
        String allowedOrigins
    ) {
        List<String> origins = Arrays.stream(
                allowedOrigins.split(",")
            )
            .map(String::strip)
            .filter(origin -> !origin.isEmpty())
            .toList();

        CorsConfiguration configuration = new CorsConfiguration();

        configuration.setAllowedOrigins(origins);

        configuration.setAllowedMethods(
            List.of("GET", "POST", "PATCH", "OPTIONS")
        );

        configuration.setAllowedHeaders(
            List.of(
                "Authorization",
                "Content-Type",
                "X-Request-Id"
            )
        );

        configuration.setExposedHeaders(
            List.of("X-Request-Id")
        );

        configuration.setAllowCredentials(true);
        configuration.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration(
            "/api/**",
            configuration
        );

        return source;
    }
}
