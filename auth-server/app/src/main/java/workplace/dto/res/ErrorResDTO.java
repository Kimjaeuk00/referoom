package workplace.dto.res;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class ErrorResDTO {

    private final boolean ok;
    private final String error;
    private final String code;
}