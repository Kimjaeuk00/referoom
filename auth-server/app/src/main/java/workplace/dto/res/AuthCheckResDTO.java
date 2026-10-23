package workplace.dto.res;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class AuthCheckResDTO {

    private final boolean ok;
    private final String via;
    private final String username;
    private final String sub;
}
