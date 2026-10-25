package workplace.security;

import java.time.Instant;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTCreator;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.exceptions.TokenExpiredException;
import com.auth0.jwt.interfaces.DecodedJWT;
import org.springframework.stereotype.Component;
import workplace.config.JwtProperties;
import workplace.entity.Team;
import workplace.entity.User;
import workplace.enums.ErrorCode;
import workplace.enums.Role;
import workplace.enums.TeamType;
import workplace.enums.ViewType;
import workplace.exception.ApiException;

@Component
public class JwtTokenProvider {

    private final JwtProperties jwtProperties;
    private final Algorithm algorithm;
    private final JWTVerifier verifier;

    public JwtTokenProvider(JwtProperties jwtProperties) {
        this.jwtProperties = jwtProperties;
        this.algorithm = Algorithm.HMAC256(
            jwtProperties.getSecret()
        );

        this.verifier = JWT.require(algorithm)
            .withIssuer(jwtProperties.getIssuer())
            .withClaimPresence("sub")
            .withClaimPresence("username")
            .withClaimPresence("role")
            .withClaimPresence("team_id")
            .withClaimPresence("team_type")
            .withClaimPresence("view")
            .withClaimPresence("iat")
            .withClaimPresence("exp")
            .build();
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

    public CustomPrincipal verifyToken(String token) {
        try {
            // 서명·알고리즘·발급자·시간 조건·필수 claim 검증
            DecodedJWT jwt = verifier.verify(token);

            long userId = Long.parseLong(
                readRequiredString(jwt, "sub")
            );

            if (userId <= 0) {
                throw new IllegalArgumentException("Invalid subject");
            }

            String username = readRequiredString(jwt, "username");

            Role role = Role.valueOf(
                readRequiredString(jwt, "role")
            );

            ViewType view = ViewType.valueOf(
                readRequiredString(jwt, "view")
            );

            long issuedAt = readPositiveInteger(jwt, "iat");
            long expiresAt = readPositiveInteger(jwt, "exp");

            if (expiresAt <= issuedAt) {
                throw new IllegalArgumentException(
                    "Invalid token lifetime"
                );
            }

            boolean teamIdIsNull = jwt.getClaim("team_id").isNull();
            boolean teamTypeIsNull = jwt.getClaim("team_type").isNull();

            if (teamIdIsNull != teamTypeIsNull) {
                throw new IllegalArgumentException(
                    "Invalid team claims"
                );
            }

            Long teamId = null;
            TeamType teamType = null;

            if (!teamIdIsNull) {
                teamId = readPositiveInteger(jwt, "team_id");

                teamType = TeamType.valueOf(
                    readRequiredString(jwt, "team_type")
                );
            }

            return new CustomPrincipal(
                userId,
                username,
                role,
                teamId,
                teamType,
                view
            );
        } catch (TokenExpiredException exception) {
            throw new ApiException(
                ErrorCode.TOKEN_EXPIRED,
                exception
            );
        } catch (
            JWTVerificationException | IllegalArgumentException exception
        ) {
            throw new ApiException(
                ErrorCode.UNAUTHORIZED,
                exception
            );
        }
    }

    public long getExpirationSeconds() {
        return jwtProperties.getExpirationSeconds();
    }

    private String readRequiredString(
        DecodedJWT jwt,
        String claimName
    ) {
        String value = jwt.getClaim(claimName).asString();

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid string claim: " + claimName
            );
        }

        return value;
    }

    private long readPositiveInteger(
        DecodedJWT jwt,
        String claimName
    ) {
        Object value = jwt.getClaim(claimName).as(Object.class);

        if (!(value instanceof Integer)
            && !(value instanceof Long)) {
            throw new IllegalArgumentException(
                "Invalid integer claim: " + claimName
            );
        }

        long number = ((Number) value).longValue();

        if (number <= 0) {
            throw new IllegalArgumentException(
                "Invalid positive claim: " + claimName
            );
        }

        return number;
    }
}
