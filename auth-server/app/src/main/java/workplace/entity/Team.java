package workplace.entity;

import java.time.LocalDateTime;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;
import workplace.enums.TeamType;

@Entity
@Table(
    name = "teams",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_teams_invite_code",
            columnNames = "invite_code"
        )
    }
)
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PROTECTED)
public class Team {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", columnDefinition = "BIGINT UNSIGNED")
    private Long id;

    @Column(name = "name", nullable = false, length = 100)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(
        name = "team_type",
        nullable = false,
        columnDefinition = "ENUM('dev','rnd')"
    )
    private TeamType teamType;

    @Column(name = "invite_code", nullable = false, length = 16)
    private String inviteCode;

    @Column(
        name = "created_at",
        nullable = false,
        insertable = false,
        updatable = false,
        columnDefinition = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )
    private LocalDateTime createdAt;

    @Column(
        name = "updated_at",
        nullable = false,
        insertable = false,
        updatable = false,
        columnDefinition =
            "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
    )
    private LocalDateTime updatedAt;

    public void changeInviteCode(String inviteCode) {
        this.inviteCode = inviteCode;
    }
}
