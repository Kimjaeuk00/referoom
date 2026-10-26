package workplace.dto.res;

import lombok.Builder;
import lombok.Getter;
import workplace.enums.Role;

@Getter
@Builder
public class UserResDTO {

    private final Long id;
    private final String username;
    private final String displayName;
    private final Role role;
    private final TeamInfo team;

    @Getter
    @Builder
    public static class TeamInfo {

        private final Long id;
        private final String name;
    }
}