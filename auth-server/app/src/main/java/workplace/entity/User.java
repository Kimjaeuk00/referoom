package workplace.entity;

import java.time.LocalDateTime;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;
import workplace.enums.Role;
import workplace.enums.SkillLevel;
import workplace.enums.ViewType;

@Entity
@Table(
    name = "users",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_users_username",
            columnNames = "username"
        )
    },
    indexes = {
        @Index(
            name = "idx_users_team",
            columnList = "team_id"
        )
    }
)
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PROTECTED)
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", columnDefinition = "BIGINT UNSIGNED")
    private Long id;

    @Column(name = "username", nullable = false, length = 100)
    private String username;

    @Column(name = "display_name", length = 100)
    private String displayName;

    @Column(name = "password", nullable = false, length = 255)
    private String password;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(
        name = "team_id",
        columnDefinition = "BIGINT UNSIGNED",
        foreignKey = @ForeignKey(name = "fk_users_team")
    )
    private Team team;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(
        name = "role",
        nullable = false,
        columnDefinition = "ENUM('member','team_admin') DEFAULT 'member'"
    )
    private Role role = Role.member;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(
        name = "skill_level",
        nullable = false,
        columnDefinition = "ENUM('L1','L2','L3') DEFAULT 'L2'"
    )
    private SkillLevel skillLevel = SkillLevel.L2;

    @Enumerated(EnumType.STRING)
    @Column(
        name = "view_pref",
        columnDefinition = "ENUM('dev','rnd')"
    )
    private ViewType viewPref;

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

    public void joinTeam(Team team) {
        this.team = team;
        this.role = Role.member;
    }

    public void updateProfile(
        SkillLevel skillLevel,
        ViewType viewPref
    ) {
        if (skillLevel != null) {
            this.skillLevel = skillLevel;
        }

        if (viewPref != null) {
            this.viewPref = viewPref;
        }
    }

    public ViewType getEffectiveView() {
    if (viewPref != null) {
        return viewPref;
    }

    if (team != null) {
        return ViewType.valueOf(team.getTeamType().name());
    }

    return ViewType.dev;
}
}
