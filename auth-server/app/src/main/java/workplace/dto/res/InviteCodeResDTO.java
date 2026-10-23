package workplace.dto.res;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class InviteCodeResDTO {

    private final boolean ok;
    private final String inviteCode;
}
