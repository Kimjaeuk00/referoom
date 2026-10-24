package workplace.dto.res;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Builder;
import lombok.Getter;
import workplace.enums.Role;

@Getter
@Builder
public class SignupResDTO {

    private final boolean ok;
    private final Long teamId;
    private final Role role;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private final String inviteCode;
}