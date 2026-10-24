package workplace.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import workplace.converter.UserConverter;
import workplace.dto.req.UpdateProfileReqDTO;
import workplace.dto.res.MeResDTO;
import workplace.dto.res.TokenUserResDTO;
import workplace.entity.User;
import workplace.enums.ErrorCode;
import workplace.enums.SkillLevel;
import workplace.enums.ViewType;
import workplace.exception.ApiException;
import workplace.repository.UserRepository;
import workplace.security.JwtTokenProvider;

@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;
    private final JwtTokenProvider jwtTokenProvider;

    @Transactional(readOnly = true)
    public MeResDTO getMe(Long userId) {
        User user = userRepository.findWithTeamById(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        return UserConverter.toMeResDTO(user);
    }

    @Transactional
    public TokenUserResDTO updateProfile(
        Long userId,
        UpdateProfileReqDTO request
    ) {
        if (request.level() == null && request.view() == null) {
            throw new ApiException(
                ErrorCode.VALIDATION_ERROR
            );
        }

        User user = userRepository.findWithTeamById(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        SkillLevel skillLevel = request.level() == null
            ? null
            : SkillLevel.valueOf(request.level());

        ViewType viewPref = request.view() == null
            ? null
            : ViewType.valueOf(request.view());

        user.updateProfile(skillLevel, viewPref);

        String accessToken = jwtTokenProvider.createToken(user);

        return UserConverter.toTokenUserResDTO(
            user,
            accessToken
        );
    }
}
