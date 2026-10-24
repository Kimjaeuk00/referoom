package workplace.dto.req;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record LoginReqDTO(

    @NotBlank
    @Size(max = 100)
    String username,

    @NotBlank
    String password

) {
    public LoginReqDTO {
        username = username == null ? null : username.strip();
    }
}