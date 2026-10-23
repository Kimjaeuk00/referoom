package workplace.repository;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import workplace.entity.User;

public interface UserRepository extends JpaRepository<User, Long> {

    boolean existsByUsername(String username);

    @EntityGraph(attributePaths = "team")
    Optional<User> findByUsername(String username);

    @EntityGraph(attributePaths = "team")
    Optional<User> findWithTeamById(Long id);

    long countByTeam_Id(Long teamId);

    @EntityGraph(attributePaths = "team")
    List<User> findAllByTeam_IdOrderByIdAsc(Long teamId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select u from User u where u.id = :userId")
    Optional<User> findByIdForUpdate(
        @Param("userId") Long userId
    );
}
