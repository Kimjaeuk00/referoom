package workplace.service;

import java.nio.charset.StandardCharsets;

import lombok.RequiredArgsConstructor;
import org.hibernate.exception.ConstraintViolationException;
import org.mindrot.jbcrypt.BCrypt;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import workplace.converter.UserConverter;
import workplace.dto.req.SignupReqDTO;
import workplace.dto.res.AuthCheckResDTO;
import workplace.dto.res.SignupResDTO;
import workplace.entity.Team;
import workplace.entity.User;
import workplace.enums.ErrorCode;
import workplace.enums.Role;
import workplace.exception.ApiException;
import workplace.repository.UserRepository;
import workplace.dto.req.LoginReqDTO;
import workplace.dto.res.LoginResDTO;
import workplace.security.JwtTokenProvider;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final TeamService teamService;
    private final JwtTokenProvider jwtTokenProvider;

    @Transactional
    public SignupResDTO signup(SignupReqDTO request) {
        validateSignup(request);

        if (userRepository.existsByUsername(request.username())) {
            throw new ApiException(ErrorCode.CONFLICT);
        }

        String encodedPassword = BCrypt.hashpw(
            request.password(),
            BCrypt.gensalt(12)
        );

        boolean teamCreated = "create".equals(request.teamMode());

        try {
            Team team = null;
            Role role = Role.member;

            if (teamCreated) {
                team = teamService.createTeam(
                    request.teamName().strip()
                );

                role = Role.team_admin;

            } else if ("join".equals(request.teamMode())) {
                team = teamService.findByInviteCode(
                    request.teamCode()
                );
            }

            User user = UserConverter.toUser(
                request,
                encodedPassword,
                team,
                role
            );

            User savedUser = userRepository.saveAndFlush(user);

            String inviteCode = teamCreated
                ? team.getInviteCode()
                : null;

            return UserConverter.toSignupResDTO(
                savedUser,
                inviteCode
            );

        } catch (DataIntegrityViolationException exception) {
            if (isUsernameConflict(exception)) {
                throw new ApiException(
                    ErrorCode.CONFLICT,
                    exception
                );
            }

            throw exception;
        }
    }

    private void validateSignup(SignupReqDTO request) {
        // BCrypt의 입력 한계를 넘어가는 비밀번호는 거절
        if (request.password()
                .getBytes(StandardCharsets.UTF_8).length > 72) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR);
        }

        if ("create".equals(request.teamMode())) {
            if (!StringUtils.hasText(request.teamName())) {
                throw new ApiException(ErrorCode.VALIDATION_ERROR);
            }
        }

        if ("join".equals(request.teamMode())) {
            if (!StringUtils.hasText(request.teamCode())) {
                throw new ApiException(ErrorCode.VALIDATION_ERROR);
            }
        }
    }

    private boolean isUsernameConflict(
        DataIntegrityViolationException exception
    ) {
        Throwable cause = exception;

        while (cause != null) {
            if (cause instanceof ConstraintViolationException violation) {
                String constraintName = violation.getConstraintName();

                if (constraintName != null
                        && constraintName.contains("uk_users_username")) {
                    return true;
                }
            }

            cause = cause.getCause();
        }

        return false;
    }   

    @Transactional(readOnly = true)
    public LoginResDTO login(LoginReqDTO request) {
        if (request.password()
                .getBytes(StandardCharsets.UTF_8).length > 72) {
            throw new ApiException(ErrorCode.INVALID_CREDENTIALS);
        }

        User user = userRepository.findByUsername(request.username())
            .orElseThrow(
                () -> new ApiException(ErrorCode.INVALID_CREDENTIALS)
            );

        boolean passwordMatches;

        try {
            passwordMatches = BCrypt.checkpw(
                request.password(),
                user.getPassword()
            );
        } catch (IllegalArgumentException exception) {
            throw new ApiException(
                ErrorCode.INVALID_CREDENTIALS,
                exception
            );
        }

        if (!passwordMatches) {
            throw new ApiException(ErrorCode.INVALID_CREDENTIALS);
        }

        String accessToken = jwtTokenProvider.createToken(user);

        return UserConverter.toLoginResDTO(
            user,
            accessToken,
            jwtTokenProvider.getExpirationSeconds()
        );
    }

    @Transactional(readOnly = true)
    public AuthCheckResDTO checkAuth(Long userId) {
        User user = userRepository.findById(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        return UserConverter.toAuthCheckResDTO(user);
    }
}
