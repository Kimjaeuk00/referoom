package workplace.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI openAPI() {
        SecurityScheme bearerScheme = new SecurityScheme()
            .type(SecurityScheme.Type.HTTP)
            .scheme("bearer")
            .bearerFormat("JWT");

        SecurityScheme cookieScheme = new SecurityScheme()
            .type(SecurityScheme.Type.APIKEY)
            .in(SecurityScheme.In.COOKIE)
            .name("ACCESS_TOKEN")
            .description("로그인 응답으로 발급되는 JWT 쿠키");

        return new OpenAPI()
            .info(
                new Info()
                    .title("Referoom 인증 API")
                    .version("v1")
            )
            .components(
                new Components()
                    .addSecuritySchemes(
                        "bearerAuth",
                        bearerScheme
                    )
                    .addSecuritySchemes(
                        "cookieAuth",
                        cookieScheme
                    )
            );
    }
}
