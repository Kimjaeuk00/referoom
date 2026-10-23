package workplace.dto.res;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class TokenUserResDTO {

    private final boolean ok;
    private final String accessToken;
    private final UserResDTO user;
}
