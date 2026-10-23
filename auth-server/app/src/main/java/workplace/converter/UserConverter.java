package workplace.converter;

import workplace.dto.req.SignupReqDTO;
import workplace.dto.res.SignupResDTO;
import workplace.entity.Team;
import workplace.entity.User;
import workplace.enums.Role;
import workplace.enums.SkillLevel;

public final class UserConverter {

    private UserConverter() {
    }

    public static User toUser(
        SignupReqDTO request,
        String encodedPassword,
        Team team,
        Role role
    ) {
        SkillLevel skillLevel = request.level() == null
            ? SkillLevel.L2
            : SkillLevel.valueOf(request.level());

        return User.builder()
            .username(request.username())
            .displayName(request.displayName())
            .password(encodedPassword)
            .team(team)
            .role(role)
            .skillLevel(skillLevel)
            .build();
    }

    public static SignupResDTO toSignupResDTO(
        User user,
        String inviteCode
    ) {
        Long teamId = user.getTeam() == null
            ? null
            : user.getTeam().getId();

        return SignupResDTO.builder()
            .ok(true)
            .teamId(teamId)
            .role(user.getRole())
            .inviteCode(inviteCode)
            .build();
    }
}