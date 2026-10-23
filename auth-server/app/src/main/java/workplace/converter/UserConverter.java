package workplace.converter;

import workplace.dto.req.SignupReqDTO;
import workplace.dto.res.AuthCheckResDTO;
import workplace.dto.res.LoginResDTO;
import workplace.dto.res.MeResDTO;
import workplace.dto.res.SignupResDTO;
import workplace.dto.res.TokenUserResDTO;
import workplace.dto.res.UserResDTO;
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

    public static UserResDTO toUserResDTO(User user) {
        return UserResDTO.builder()
            .id(user.getId())
            .username(user.getUsername())
            .displayName(user.getDisplayName())
            .role(user.getRole())
            .level(user.getSkillLevel())
            .view(user.getEffectiveView())
            .team(TeamConverter.toTeamInfoDTO(user.getTeam()))
            .build();
    }

    public static LoginResDTO toLoginResDTO(
        User user,
        String accessToken,
        long expiresIn
    ) {
        return LoginResDTO.builder()
            .ok(true)
            .accessToken(accessToken)
            .tokenType("Bearer")
            .expiresIn(expiresIn)
            .user(toUserResDTO(user))
            .build();
    }

    public static TokenUserResDTO toTokenUserResDTO(
        User user,
        String accessToken
    ) {
        return TokenUserResDTO.builder()
            .ok(true)
            .accessToken(accessToken)
            .user(toUserResDTO(user))
            .build();
    }

    public static MeResDTO toMeResDTO(User user) {
        return MeResDTO.builder()
            .user(toUserResDTO(user))
            .build();
    }

    public static AuthCheckResDTO toAuthCheckResDTO(User user) {
        return AuthCheckResDTO.builder()
            .ok(true)
            .via("jwt")
            .username(user.getUsername())
            .sub(user.getId().toString())
            .build();
    }
}
