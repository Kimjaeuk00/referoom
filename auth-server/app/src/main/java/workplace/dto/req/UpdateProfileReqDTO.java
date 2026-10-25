package workplace.dto.req;

import jakarta.validation.constraints.Pattern;

public record UpdateProfileReqDTO(

    @Pattern(
        regexp = "dev|rnd",
        message = "view는 dev, rnd 중 하나여야 합니다."
    )
    String view

) {
}
