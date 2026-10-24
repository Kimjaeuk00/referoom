package workplace.dto.req;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record JoinTeamReqDTO(

    @NotBlank(message = "초대 코드를 입력해 주세요.")
    @Size(
        max = 16,
        message = "초대 코드는 16자 이하여야 합니다."
    )
    String teamCode

) {

    public JoinTeamReqDTO {
        if (teamCode != null) {
            teamCode = teamCode.strip();
        }
    }
}
