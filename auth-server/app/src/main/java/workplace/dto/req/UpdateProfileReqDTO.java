package workplace.dto.req;

import jakarta.validation.constraints.Pattern;

public record UpdateProfileReqDTO(

    @Pattern(
        regexp = "L1|L2|L3",
        message = "level은 L1, L2, L3 중 하나여야 합니다."
    )
    String level,

    @Pattern(
        regexp = "dev|rnd",
        message = "view는 dev, rnd 중 하나여야 합니다."
    )
    String view

) {
}
