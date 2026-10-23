package workplace.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import workplace.entity.User;

public interface UserRepository extends JpaRepository<User, Long> {

    boolean existsByUsername(String username);
}