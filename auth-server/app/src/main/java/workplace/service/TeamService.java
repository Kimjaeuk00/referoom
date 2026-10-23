package workplace.service;

import java.security.SecureRandom;
import java.util.Locale;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import workplace.converter.TeamConverter;
import workplace.entity.Team;
import workplace.enums.ErrorCode;
import workplace.enums.TeamType;
import workplace.exception.ApiException;
import workplace.repository.TeamRepository;

@Service
@RequiredArgsConstructor
public class TeamService {

    private static final SecureRandom RANDOM = new SecureRandom();

    private static final String INVITE_CHARACTERS =
        "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

    private final TeamRepository teamRepository;

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