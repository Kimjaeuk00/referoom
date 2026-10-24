"""시드 논문을 Zotero 그룹으로 옮기고, 팀 색인을 Zotero 키 기반 paper_id로 다시 만든다 (일회성 이전 도구).

실행 (rag-service/ 에서):
  python -m app.data.migrate_seed                 # 기본: 계획만 출력한다 (Zotero·색인에 아무것도 쓰지 않는다)
  python -m app.data.migrate_seed --apply         # 실제로 옮긴다

--apply 순서와 안전장치:
  1. 현재 색인·보관 PDF를 백업한다 (.cache/local_index_backup/<시각>/)
  2. 시드 PDF를 Zotero에 등록한다. Zotero에 같은 PDF(md5)가 이미 있으면 올리지 않는다
  3. Zotero에 모든 시드가 올라간 것을 확인한다. 하나라도 빠졌으면 여기서 멈추고 색인은 그대로 둔다
  4. 색인을 비우고 Zotero 동기화로 다시 만든다 (Zotero에서 내려받아 색인하는 실제 경로)
  5. 배치·논문별 청크 수·PDF 페이지 렌더링을 확인한다. 실패하면 백업에서 자동 복구한다
시드 PDF는 파일명이 {arxiv_id}v{n}_*.pdf 이고 app/rag/local_store/seed_papers.py 목록에 있는 것만 쓴다.
"""
import os

# 페이지 이미지 확인이 로컬 색인의 보관 PDF를 보도록 app 모듈을 import하기 전에 정한다
os.environ.setdefault("RAG_STORE", "local")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import hashlib  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from app.data import ingest, repo  # noqa: E402
from app.data.providers.arxiv import PaperCandidate  # noqa: E402
from app.data.providers.zotero import arxiv_id_of  # noqa: E402
from app.rag import config_rag, page_images  # noqa: E402
from app.rag.local_store import seed_papers, store  # noqa: E402


@dataclass
class Seed:
    path: Path
    arxiv_id: str
    version: str
    title: str
    year: int
    authors: str
    old_paper_id: int
    data: bytes

    @property
    def md5(self) -> str:
        return hashlib.md5(self.data).hexdigest()

    def candidate(self) -> PaperCandidate:
        """초록·DOI는 시드 목록에 없어 비워 둔다 (Zotero 항목의 제목·저자·연도·링크만 채워진다)."""
        return PaperCandidate(
            candidate_id=self.arxiv_id, version=self.version, title=self.title,
            authors=[a.strip() for a in self.authors.split(",") if a.strip()], year=self.year, abstract="",
            url=f"https://arxiv.org/abs/{self.arxiv_id}{self.version}", pdf_url=f"https://arxiv.org/pdf/{self.arxiv_id}{self.version}")


class LocalPdfs:
    """save_arxiv_paper에 arXiv 대신 넘기는 원본: 로컬 시드 PDF를 그대로 돌려준다 (버전 고정, 다시 받지 않는다)."""

    def __init__(self, seeds: list[Seed]):
        self._by_key = {(s.arxiv_id, s.version): s.data for s in seeds}

    async def download_pdf_bytes(self, candidate: PaperCandidate, **_) -> bytes:
        return self._by_key[(candidate.candidate_id, candidate.version)]


def load_seeds(seed_dir: Path) -> list[Seed]:
    seeds = []
    for pdf in sorted(Path(seed_dir).glob("*.pdf")):
        info = seed_papers.identify(pdf.name)
        if info is None:
            continue
        seeds.append(Seed(pdf, info["arxiv_id"], info["version"], info["title"], info["year"], info.get("authors", ""),
                          info["paper_id"], pdf.read_bytes()))
    return seeds


# ---- 계획 ----
async def _library() -> tuple[list[dict], dict[str, list[dict]]]:
    async with repo.provider_for(config_rag.ZOTERO_TEAM_ID) as provider:
        papers, attachments, _ = await provider.list_library()
    return papers, attachments


def plan_for(seeds: list[Seed], papers: list[dict], attachments: dict[str, list[dict]]) -> list[dict]:
    """시드마다 할 일. action: reuse(Zotero에 같은 PDF가 있어 쓰기 없음) | attach(항목은 있고 이 PDF만 올림) | create(항목부터 만듦)."""
    by_arxiv: dict[str, list[dict]] = {}
    for item in papers:
        arxiv_id = arxiv_id_of(item["data"])
        if arxiv_id:
            by_arxiv.setdefault(arxiv_id, []).append(item)
    plan = []
    for seed in seeds:
        found = by_arxiv.get(seed.arxiv_id, [])
        entry = {"seed": seed, "zotero_key": None, "action": "create", "warnings": []}
        if len(found) > 1:
            entry["warnings"].append(f"Zotero에 같은 arXiv 논문이 {len(found)}개 있습니다. 정리한 뒤 다시 실행하세요.")
        elif found:
            item = found[0]
            entry["zotero_key"] = item["key"]
            same_pdf = any(a["data"].get("md5") == seed.md5 for a in attachments.get(item["key"], []))
            entry["action"] = "reuse" if same_pdf else "attach"
            if item["data"].get("title", "").strip() != seed.title:
                entry["warnings"].append(f"Zotero 제목이 시드 제목과 다릅니다 ('{item['data'].get('title', '')}'). 평가 질문은 제목으로 근거를 판정합니다.")
        plan.append(entry)
    return plan


def _index_state(team_id: int) -> dict[int, int]:
    return store.paper_chunk_counts(team_id)


# ---- 백업·복구 ----
def _backup_root() -> Path:
    return Path(config_rag.LOCAL_INDEX_DIR).parent / "local_index_backup"


def backup(team_id: int) -> Path:
    target = _backup_root() / datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # 마이크로초까지: 연달아 실행해도 이름이 겹치지 않는다
    for source, name in ((Path(config_rag.LOCAL_INDEX_DIR) / str(team_id), "index"), (Path(config_rag.PDF_DIR) / str(team_id), "pdfs")):
        if source.exists():
            shutil.copytree(source, target / name)
    target.mkdir(parents=True, exist_ok=True)
    return target


def restore(team_id: int, backup_dir: Path) -> None:
    for destination, name in ((Path(config_rag.LOCAL_INDEX_DIR) / str(team_id), "index"), (Path(config_rag.PDF_DIR) / str(team_id), "pdfs")):
        shutil.rmtree(destination, ignore_errors=True)
        if (backup_dir / name).exists():
            shutil.copytree(backup_dir / name, destination)
    store.reload(team_id)


def check_page_image(team_id: int, paper_id: int) -> bool:
    """보관한 원본 PDF 1쪽을 이미지로 렌더링할 수 있는가 (질문 시 페이지 이미지 기능이 쓰는 경로)."""
    page_images.render_page.cache_clear()
    return page_images.render_page(team_id, paper_id, 1) is not None


# ---- 실행 ----
def print_plan(plan: list[dict], team_id: int, library_size: int, say=print) -> None:
    labels = {"reuse": "그대로 사용 (Zotero에 같은 PDF 있음)", "attach": "PDF만 올림 (항목은 Zotero에 있음)", "create": "새로 등록"}
    say(f"== 시드 이전 계획 (team {team_id}, Zotero 그룹 {config_rag.ZOTERO_GROUP_ID}, 현재 논문 {library_size}편) ==")
    say("[Zotero]")
    for entry in plan:
        seed = entry["seed"]
        say(f"  {seed.arxiv_id} {seed.version:3s} {seed.title[:58]:58s} → {labels[entry['action']]}")
        for warning in entry["warnings"]:
            say(f"      ! {warning}")
    counts = _index_state(team_id)
    say("[색인]")
    say(f"  현재 색인: 논문 {len(counts)}편, 청크 {sum(counts.values())}개 (paper_id {sorted(counts)}) → 비우고 Zotero 키 기반 id로 다시 만듭니다")
    say("  Zotero에 이미 있고 색인 전인 다른 논문(예: RETA-LLM)도 함께 색인됩니다")


async def migrate(seed_dir: Path, team_id: int, apply: bool, say=print) -> bool:
    """계획을 출력하고, apply면 실제로 옮긴다. 반환: 성공(또는 dry-run) 여부."""
    seeds = load_seeds(seed_dir)
    if not seeds:
        say(f"시드 PDF가 없습니다: {seed_dir}")
        return False
    papers, attachments = await _library()
    plan = plan_for(seeds, papers, attachments)
    print_plan(plan, team_id, len(papers), say)
    if any("정리한 뒤" in w for e in plan for w in e["warnings"]):
        say("중복된 Zotero 항목이 있어 중단합니다.")
        return False
    if not apply:
        say("\n(dry-run) 아무것도 쓰지 않았습니다. 실제로 옮기려면 --apply 를 붙이세요.")
        return True

    old_counts = _index_state(team_id)
    backup_dir = backup(team_id)
    say(f"\n[1/5] 백업 완료: {backup_dir}")

    todo = [e for e in plan if e["action"] != "reuse"]
    async with repo.provider_for(team_id) as provider:
        for entry in todo:
            seed = entry["seed"]
            result = await provider.save_arxiv_paper(seed.candidate(), LocalPdfs(seeds), pinned_version=seed.version)
            say(f"[2/5] Zotero 등록 {seed.arxiv_id}: {result['status']}")
    papers, attachments = await _library()
    missing = [e["seed"].arxiv_id for e in plan_for(seeds, papers, attachments) if e["action"] != "reuse"]
    if missing:
        say(f"[3/5] Zotero 확인 실패 — 아래 논문의 PDF가 확인되지 않아 중단합니다. 색인은 그대로입니다: {missing}")
        return False
    say("[3/5] Zotero에 모든 시드가 있습니다")

    repo.invalidate(team_id)
    try:
        await asyncio.to_thread(store.drop_team, team_id)
        batch_id = await ingest.start_sync(team_id)
        await ingest.drain()
        batch = ingest.get_batch(team_id, batch_id)
        say(f"[4/5] 동기화: {batch['status']} (색인 {batch['indexed']}, 실패 {batch['failed']}, 요청 {batch['requested']})")
        rows = {r["arxiv_id"]: r for r in await repo.load_rows(team_id, force=True) if r["arxiv_id"]}
        problems = _verify(team_id, seeds, old_counts, batch, rows, say)
    except Exception as error:  # noqa: BLE001  복구가 목적이므로 어떤 오류든 백업으로 되돌린다
        problems = [f"예상 밖 오류: {type(error).__name__}"]
    if problems:
        for problem in problems:
            say(f"  ✗ {problem}")
        restore(team_id, backup_dir)
        repo.invalidate(team_id)
        say(f"[5/5] 실패 — 백업에서 색인을 복구했습니다 ({backup_dir}). Zotero에 등록된 논문은 그대로 남아 있습니다.")
        return False
    say("[5/5] 검증 통과. 이전 완료")
    return True


def _verify(team_id: int, seeds: list[Seed], old_counts: dict[int, int], batch: dict, rows: dict[str, dict], say) -> list[str]:
    """배치 결과와 논문별 청크 수·페이지 이미지를 확인한다. 반환: 복구가 필요한 문제 목록 (청크 수 차이는 경고만)."""
    problems = []
    if batch["status"] != "done" or batch["failed"]:
        problems.append(f"동기화 배치가 정상 종료되지 않았습니다 (status={batch['status']}, failed={batch['failed']}, error={batch['error_msg']})")
    say(f"  {'논문':58s} {'이전':>5s} {'이후':>5s}  페이지이미지")
    for seed in seeds:
        row = rows.get(seed.arxiv_id)
        indexed = row is not None and row["status"] == "indexed"
        new_count = row["chunk_count"] if indexed else None
        old_count = old_counts.get(seed.old_paper_id)
        image_ok = indexed and check_page_image(team_id, row["id"])
        mark = "" if new_count == old_count else "  ← 청크 수가 다릅니다"
        say(f"  {seed.title[:58]:58s} {str(old_count):>5s} {str(new_count):>5s}  {'ok' if image_ok else '실패'}{mark}")
        if not indexed:
            problems.append(f"{seed.title}: 색인되지 않았습니다")
        elif not image_ok:
            problems.append(f"{seed.title}: 보관한 PDF의 페이지를 이미지로 만들 수 없습니다")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="시드 논문을 Zotero로 옮기고 색인을 다시 만든다 (기본은 dry-run)")
    parser.add_argument("--team-id", type=int, default=config_rag.ZOTERO_TEAM_ID)
    parser.add_argument("--seed-dir", type=Path, default=config_rag.SEED_DIR)
    parser.add_argument("--apply", action="store_true", help="실제로 Zotero에 등록하고 색인을 다시 만든다")
    args = parser.parse_args()
    if not repo.is_configured(args.team_id):
        sys.exit("이 팀에는 Zotero 그룹이 연결돼 있지 않습니다 (ZOTERO_GROUP_ID, ZOTERO_API_KEY, ZOTERO_TEAM_ID 확인).")
    sys.exit(0 if asyncio.run(migrate(args.seed_dir, args.team_id, args.apply)) else 1)


if __name__ == "__main__":
    main()
