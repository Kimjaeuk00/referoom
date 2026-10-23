package workplace.dto.res;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class MeResDTO {

    private final UserResDTO user;
}
