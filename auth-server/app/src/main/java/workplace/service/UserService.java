package workplace.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import workplace.converter.UserConverter;
import workplace.dto.res.MeResDTO;
import workplace.entity.User;
import workplace.enums.ErrorCode;
import workplace.exception.ApiException;
import workplace.repository.UserRepository;

@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;

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
}
