package workplace.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import workplace.converter.UserConverter;
import workplace.dto.res.MeResDTO;
import workplace.dto.res.TokenUserResDTO;
import workplace.entity.User;
import workplace.enums.ErrorCode;
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
    public TokenUserResDTO updateProfile(Long userId) {
        // 수정할 프로필 항목이 아직 없다. 최신 정보로 토큰만 다시 발급한다.
        User user = userRepository.findWithTeamById(userId)
            .orElseThrow(
                () -> new ApiException(
                    ErrorCode.UNAUTHORIZED
                )
            );

        String accessToken = jwtTokenProvider.createToken(user);

        return UserConverter.toTokenUserResDTO(
            user,
            accessToken
        );
    }
}
