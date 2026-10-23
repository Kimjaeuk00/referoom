package workplace.dto.res;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class LoginResDTO {

    private final boolean ok;
    private final String accessToken;
    private final String tokenType;
    private final long expiresIn;
    private final UserResDTO user;
}