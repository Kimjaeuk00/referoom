# Root build context. Application sources and Java configuration are unchanged.
FROM eclipse-temurin:21-jdk-jammy AS build
WORKDIR /workspace
COPY auth-server/gradlew auth-server/settings.gradle auth-server/gradle.properties ./
COPY auth-server/gradle/ ./gradle/
COPY auth-server/app/build.gradle ./app/build.gradle
COPY auth-server/app/src/ ./app/src/
RUN chmod +x gradlew \
 && ./gradlew :app:bootJar --no-daemon --no-configuration-cache

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
RUN groupadd --system app \
 && useradd --system --gid app --no-create-home app
COPY --from=build --chown=app:app /workspace/app/build/libs/*.jar /app/app.jar
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
