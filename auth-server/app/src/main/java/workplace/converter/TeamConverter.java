package workplace.converter;

import workplace.dto.res.TeamResDTO;
import workplace.dto.res.UserResDTO;
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

    public static TeamResDTO toTeamResDTO(
        Team team,
        long memberCount,
        String inviteCode
    ) {
        TeamResDTO.TeamInfo teamInfo =
            TeamResDTO.TeamInfo.builder()
                .id(team.getId())
                .name(team.getName())
                .type(team.getTeamType())
                .memberCount(memberCount)
                .inviteCode(inviteCode)
                .build();

        return TeamResDTO.builder()
            .team(teamInfo)
            .build();
    }
}
