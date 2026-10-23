package workplace.converter;

import java.util.List;

import workplace.dto.res.InviteCodeResDTO;
import workplace.dto.res.TeamMembersResDTO;
import workplace.dto.res.TeamResDTO;
import workplace.dto.res.UserResDTO;
import workplace.entity.Team;
import workplace.entity.User;
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

    public static TeamMembersResDTO toTeamMembersResDTO(
        List<User> users
    ) {
        List<TeamMembersResDTO.MemberInfo> items = users.stream()
            .map(TeamConverter::toMemberInfoDTO)
            .toList();

        return TeamMembersResDTO.builder()
            .items(items)
            .total(items.size())
            .build();
    }

    private static TeamMembersResDTO.MemberInfo toMemberInfoDTO(
        User user
    ) {
        return TeamMembersResDTO.MemberInfo.builder()
            .id(user.getId())
            .username(user.getUsername())
            .displayName(user.getDisplayName())
            .role(user.getRole())
            .level(user.getSkillLevel())
            .view(user.getEffectiveView())
            .build();
    }

    public static InviteCodeResDTO toInviteCodeResDTO(
        String inviteCode
    ) {
        return InviteCodeResDTO.builder()
            .ok(true)
            .inviteCode(inviteCode)
            .build();
    }
}
