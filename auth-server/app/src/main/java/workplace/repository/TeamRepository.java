package workplace.repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import workplace.entity.Team;

public interface TeamRepository extends JpaRepository<Team, Long> {

    Optional<Team> findByInviteCode(String inviteCode);

    boolean existsByInviteCode(String inviteCode);
}