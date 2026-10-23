package workplace.converter;

import workplace.entity.Team;
import workplace.enums.TeamType;
import workplace.dto.res.UserResDTO;

public final class TeamConverter {

    private TeamConverter() {
    }

    public static Team toTeam(
        String name,
        TeamType teamType,
        String inviteCode
    ) {
        return Team.builder()
            .name(name)
            .teamType(teamType)
            .inviteCode(inviteCode)
            .build();
    }

    public static UserResDTO.TeamInfo toTeamInfoDTO(Team team) {
    if (team == null) {
        return null;
    }

    return UserResDTO.TeamInfo.builder()
        .id(team.getId())
        .name(team.getName())
        .type(team.getTeamType())
        .build();
}
}