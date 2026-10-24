package workplace.dto.req;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record SignupReqDTO(

    @NotBlank
    @Size(min = 4, max = 50)
    String username,

    @NotBlank
    @Size(min = 8)
    String password,

    @Size(max = 100)
    String displayName,

    @Pattern(regexp = "L1|L2|L3")
    String level,

    @Pattern(regexp = "create|join")
    String teamMode,

    @Size(max = 100)
    String teamName,

    @Pattern(regexp = "dev|rnd")
    String teamType,

    @Size(max = 16)
    String teamCode

) {
    public SignupReqDTO {
        username = username == null ? null : username.strip();
    }
}