package workplace.dto.res;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class HealthResDTO {

    private final boolean ok;
    private final String db;
}