package workplace.security;

import java.security.Principal;

import workplace.enums.Role;

public record CustomPrincipal(
    Long userId,
    String username,
    Role role,
    Long teamId
) implements Principal {

    @Override
    public String getName() {
        return userId.toString();
    }
}
