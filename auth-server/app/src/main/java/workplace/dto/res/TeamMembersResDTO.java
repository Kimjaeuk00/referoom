package workplace.dto.res;

import java.util.List;

import lombok.Builder;
import lombok.Getter;
import workplace.enums.Role;
import workplace.enums.SkillLevel;
import workplace.enums.ViewType;

@Getter
@Builder
public class TeamMembersResDTO {

    private final List<MemberInfo> items;
    private final long total;

    @Getter
    @Builder
    public static class MemberInfo {

        private final Long id;
        private final String username;
        private final String displayName;
        private final Role role;
        private final SkillLevel level;
        private final ViewType view;
    }
}
