package workplace.dto.res;

import lombok.Builder;
import lombok.Getter;
import workplace.enums.Role;
import workplace.enums.TeamType;
import workplace.enums.ViewType;

@Getter
@Builder
public class UserResDTO {

    private final Long id;
    private final String username;
    private final String displayName;
    private final Role role;
    private final ViewType view;
    private final TeamInfo team;

    @Getter
    @Builder
    public static class TeamInfo {

        private final Long id;
        private final String name;
        private final TeamType type;
    }
}