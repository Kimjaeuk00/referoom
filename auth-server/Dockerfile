# 1단계: Spring Boot 실행 JAR 빌드
FROM eclipse-temurin:21-jdk-jammy AS build

WORKDIR /workspace

# Gradle Wrapper와 빌드 설정
COPY gradlew settings.gradle gradle.properties ./
COPY gradle/ ./gradle/
COPY app/build.gradle ./app/build.gradle

# 애플리케이션 소스
COPY app/src/ ./app/src/

RUN chmod +x gradlew \
    && ./gradlew :app:bootJar \
        --no-daemon \
        --no-configuration-cache


# 2단계: 실행 환경
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app

# 애플리케이션 실행 전용 사용자
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home app

# 빌드 단계에서 생성한 실행 JAR만 복사
COPY --from=build --chown=app:app \
    /workspace/app/build/libs/*.jar \
    /app/app.jar

USER app

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
