package workplace.dto.res;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Builder;
import lombok.Getter;
import workplace.enums.TeamType;

@Getter
@Builder
public class TeamResDTO {

    private final TeamInfo team;

    @Getter
    @Builder
    public static class TeamInfo {

        private final Long id;
        private final String name;
        private final TeamType type;
        private final long memberCount;

        @JsonInclude(JsonInclude.Include.NON_NULL)
        private final String inviteCode;
    }
}
