package workplace.converter;

import workplace.entity.Team;
import workplace.enums.TeamType;

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
}