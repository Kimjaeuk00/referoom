package workplace.security;

import java.security.Principal;

import workplace.enums.Role;
import workplace.enums.SkillLevel;
import workplace.enums.TeamType;
import workplace.enums.ViewType;

public record CustomPrincipal(
    Long userId,
    String username,
    Role role,
    Long teamId,
    TeamType teamType,
    SkillLevel level,
    ViewType view
) implements Principal {

    @Override
    public String getName() {
        return userId.toString();
    }
}
