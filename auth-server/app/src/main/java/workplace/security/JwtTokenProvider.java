package workplace.security;

import java.time.Instant;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTCreator;
import com.auth0.jwt.algorithms.Algorithm;
import org.springframework.stereotype.Component;
import workplace.config.JwtProperties;
import workplace.entity.Team;
import workplace.entity.User;

@Component
public class JwtTokenProvider {

    private final JwtProperties jwtProperties;
    private final Algorithm algorithm;

    public JwtTokenProvider(JwtProperties jwtProperties) {
        this.jwtProperties = jwtProperties;
        this.algorithm = Algorithm.HMAC256(
            jwtProperties.getSecret()
        );
    }

    public String createToken(User user) {
        Instant issuedAt = Instant.now();
        Instant expiresAt = issuedAt.plusSeconds(
            jwtProperties.getExpirationSeconds()
        );

        JWTCreator.Builder builder = JWT.create()
            .withIssuer(jwtProperties.getIssuer())
            .withSubject(user.getId().toString())
            .withClaim("username", user.getUsername())
            .withClaim("role", user.getRole().name())
            .withClaim("level", user.getSkillLevel().name())
            .withClaim("view", user.getEffectiveView().name())
            .withIssuedAt(issuedAt)
            .withExpiresAt(expiresAt);

        Team team = user.getTeam();

        if (team == null) {
            builder
                .withNullClaim("team_id")
                .withNullClaim("team_type");
        } else {
            builder
                .withClaim("team_id", team.getId())
                .withClaim("team_type", team.getTeamType().name());
        }

        return builder.sign(algorithm);
    }

    public long getExpirationSeconds() {
        return jwtProperties.getExpirationSeconds();
    }
}