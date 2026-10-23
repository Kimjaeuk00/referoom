package workplace.repository;

import java.util.Optional;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import workplace.entity.Team;

public interface TeamRepository extends JpaRepository<Team, Long> {

    Optional<Team> findByInviteCode(String inviteCode);

    boolean existsByInviteCode(String inviteCode);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select t from Team t where t.id = :teamId")
    Optional<Team> findByIdForUpdate(
        @Param("teamId") Long teamId
    );
}
