package workplace.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import workplace.dto.req.JoinTeamReqDTO;
import workplace.dto.res.InviteCodeResDTO;
import workplace.dto.res.TeamMembersResDTO;
import workplace.dto.res.TeamResDTO;
import workplace.dto.res.TokenUserResDTO;
import workplace.security.AuthCookieManager;
import workplace.security.CustomPrincipal;
import workplace.service.TeamService;

@RestController
@RequestMapping("/api/team")
@RequiredArgsConstructor
@Tag(name = "팀", description = "팀 정보 및 팀 관리 API")
public class TeamController {

    private final TeamService teamService;
    private final AuthCookieManager authCookieManager;

    @GetMapping
    @Operation(summary = "내 팀 정보 조회")
    @SecurityRequirement(name = "bearerAuth")
    public TeamResDTO getMyTeam(
        @Parameter(hidden = true)
        @AuthenticationPrincipal CustomPrincipal principal
    ) {
        return teamService.getMyTeam(
            principal.userId(),
            principal.teamId(),
            principal.role()
        );
    }

    @PostMapping("/join")
    @Operation(summary = "초대 코드로 팀 참여")
    @SecurityRequirement(name = "bearerAuth")
    public TokenUserResDTO joinTeam(
        @Parameter(hidden = true)
        @AuthenticationPrincipal CustomPrincipal principal,
        @Valid @RequestBody JoinTeamReqDTO request,
        HttpServletRequest servletRequest,
        HttpServletResponse servletResponse
    ) {
        TokenUserResDTO result = teamService.joinTeam(
            principal.userId(),
            request
        );

        authCookieManager.setAccessTokenCookie(
            servletResponse,
            result.getAccessToken(),
            servletRequest.isSecure()
        );

        return result;
    }

    @GetMapping("/members")
    @Operation(summary = "내 팀원 목록 조회 — 관리자 전용")
    @SecurityRequirement(name = "bearerAuth")
    public TeamMembersResDTO getTeamMembers(
        @Parameter(hidden = true)
        @AuthenticationPrincipal CustomPrincipal principal
    ) {
        return teamService.getTeamMembers(
            principal.userId(),
            principal.teamId(),
            principal.role()
        );
    }

    @PostMapping("/invite-code/rotate")
    @Operation(summary = "팀 초대 코드 재발급 — 관리자 전용")
    @SecurityRequirement(name = "bearerAuth")
    public InviteCodeResDTO rotateInviteCode(
        @Parameter(hidden = true)
        @AuthenticationPrincipal CustomPrincipal principal
    ) {
        return teamService.rotateInviteCode(
            principal.userId(),
            principal.teamId(),
            principal.role()
        );
    }
}
