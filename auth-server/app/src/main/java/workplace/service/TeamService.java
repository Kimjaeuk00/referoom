package workplace.service;

import java.security.SecureRandom;
import java.util.List;
import java.util.Locale;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import workplace.converter.TeamConverter;
import workplace.converter.UserConverter;
import workplace.dto.req.JoinTeamReqDTO;
import workplace.dto.res.InviteCodeResDTO;
import workplace.dto.res.TeamMembersResDTO;
import workplace.dto.res.TeamResDTO;
import workplace.dto.res.TokenUserResDTO;
import workplace.entity.Team;
import workplace.entity.User;
import workplace.enums.ErrorCode;
import workplace.enums.Role;
import workplace.enums.TeamType;
import workplace.exception.ApiException;
import workplace.repository.TeamRepository;
import workplace.repository.UserRepository;
import workplace.security.JwtTokenProvider;

@Service
@RequiredArgsConstructor
public class TeamService {

    private static final SecureRandom RANDOM = new SecureRandom();

    private static final String INVITE_CHARACTERS =
        "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

    private final TeamRepository teamRepository;
    private final UserRepository userRepository;
    private final JwtTokenProvider jwtTokenProvider;

    @Transactional
    public Team createTeam(String name, TeamType teamType) {
        String inviteCode = generateInviteCode();

        Team team = TeamConverter.toTeam(
            name,
            teamType,
            inviteCode
        );

        return teamRepository.save(team);
    }

    @Transactional(readOnly = true)
    public Team findByInviteCode(String inviteCode) {
        String normalizedCode = inviteCode
            .strip()
            .toUpperCase(Locale.ROOT);

        return teamRepository.findByInviteCode(normalizedCode)
            .orElseThrow(
                () -> new ApiException(ErrorCode.TEAM_NOT_FOUND)
            );
    }

    @Transactional(readOnly = true)
    public TeamResDTO getMyTeam(
        Long userId,
        Long jwtTeamId,
        Role jwtRole
    ) {
        User user = userRepository.findWithTeamById(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        Team team = user.getTeam();

        if (jwtTeamId == null || team == null) {
            throw new ApiException(
                ErrorCode.NO_TEAM
            );
        }

        if (!jwtTeamId.equals(team.getId())) {
            throw new ApiException(
                ErrorCode.FORBIDDEN
            );
        }

        long memberCount = userRepository.countByTeam_Id(
            jwtTeamId
        );

        boolean isAdmin =
            jwtRole == Role.team_admin
            && user.getRole() == Role.team_admin;

        String inviteCode = isAdmin
            ? team.getInviteCode()
            : null;

        return TeamConverter.toTeamResDTO(
            team,
            memberCount,
            inviteCode
        );
    }

    @Transactional
    public TokenUserResDTO joinTeam(
        Long userId,
        JoinTeamReqDTO request
    ) {
        User user = userRepository.findByIdForUpdate(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        if (user.getTeam() != null) {
            throw new ApiException(
                ErrorCode.ALREADY_IN_TEAM
            );
        }

        Team team = findByInviteCode(
            request.teamCode()
        );

        user.joinTeam(team);

        String accessToken = jwtTokenProvider.createToken(user);

        return UserConverter.toTokenUserResDTO(
            user,
            accessToken
        );
    }

    @Transactional(readOnly = true)
    public TeamMembersResDTO getTeamMembers(
        Long userId,
        Long jwtTeamId,
        Role jwtRole
    ) {
        User user = userRepository.findWithTeamById(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        Team team = user.getTeam();

        if (jwtTeamId == null || team == null) {
            throw new ApiException(
                ErrorCode.NO_TEAM
            );
        }

        if (!jwtTeamId.equals(team.getId())) {
            throw new ApiException(
                ErrorCode.FORBIDDEN
            );
        }

        if (jwtRole != Role.team_admin
                || user.getRole() != Role.team_admin) {
            throw new ApiException(
                ErrorCode.FORBIDDEN
            );
        }

        List<User> members =
            userRepository.findAllByTeam_IdOrderByIdAsc(
                jwtTeamId
            );

        return TeamConverter.toTeamMembersResDTO(
            members
        );
    }

    @Transactional
    public InviteCodeResDTO rotateInviteCode(
        Long userId,
        Long jwtTeamId,
        Role jwtRole
    ) {
        User user = userRepository.findByIdForUpdate(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        Team currentTeam = user.getTeam();

        if (jwtTeamId == null || currentTeam == null) {
            throw new ApiException(
                ErrorCode.NO_TEAM
            );
        }

        if (!jwtTeamId.equals(currentTeam.getId())) {
            throw new ApiException(
                ErrorCode.FORBIDDEN
            );
        }

        if (jwtRole != Role.team_admin
                || user.getRole() != Role.team_admin) {
            throw new ApiException(
                ErrorCode.FORBIDDEN
            );
        }

        Team team = teamRepository.findByIdForUpdate(jwtTeamId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.FORBIDDEN
                )
            );

        String newInviteCode = generateInviteCode();

        team.changeInviteCode(newInviteCode);

        teamRepository.flush();

        return TeamConverter.toInviteCodeResDTO(
            newInviteCode
        );
    }

    private String generateInviteCode() {
        for (int attempt = 0; attempt < 5; attempt++) {
            StringBuilder builder = new StringBuilder(8);

            for (int index = 0; index < 8; index++) {
                int position = RANDOM.nextInt(
                    INVITE_CHARACTERS.length()
                );

                builder.append(
                    INVITE_CHARACTERS.charAt(position)
                );
            }

            String inviteCode = builder.toString();

            if (!teamRepository.existsByInviteCode(inviteCode)) {
                return inviteCode;
            }
        }

        throw new ApiException(ErrorCode.INTERNAL_SERVER_ERROR);
    }
}
