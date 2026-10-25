"""시드 이전 도구 테스트: 가짜 Zotero·색인·로컬 폴더만 쓴다 (실제 그룹·색인은 건드리지 않는다)."""
import asyncio
import hashlib

import pytest

from app.data import ingest, migrate_seed, repo
from app.data.ids import paper_id_from_key
from app.rag import config_rag
from zotero_fake import SCAN, FakeStore, FakeZotero, make_pdf

TEAM = 3
SEED_FILES = {"1902.00751": ("v2", "adapter"), "2101.00190": ("v1", "prefix-tuning"), "2104.08691": ("v2", "prompt-tuning"),
              "2106.09685": ("v2", "lora"), "2305.14314": ("v1", "qlora")}
TITLES = {"1902.00751": "Parameter-Efficient Transfer Learning for NLP"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    for n, (arxiv_id, (version, name)) in enumerate(SEED_FILES.items()):
        (seed_dir / f"{arxiv_id}{version}_{name}.pdf").write_bytes(make_pdf(n + 3))
    index_dir, pdf_dir = tmp_path / "cache" / "local_index", tmp_path / "cache" / "pdfs"
    (index_dir / str(TEAM)).mkdir(parents=True)
    (index_dir / str(TEAM) / "meta.json").write_text("OLD INDEX")
    (pdf_dir / str(TEAM)).mkdir(parents=True)
    (pdf_dir / str(TEAM) / "1.pdf").write_bytes(b"OLD PDF")
    fake, fake_store = FakeZotero(), FakeStore()
    fake_store.counts = {1: 65, 2: 67, 3: 76, 4: 112, 5: 106}  # 이전 색인 (paper_id 1~5)
    monkeypatch.setattr(config_rag, "LOCAL_INDEX_DIR", index_dir)
    monkeypatch.setattr(config_rag, "PDF_DIR", pdf_dir)
    monkeypatch.setattr(config_rag, "ZOTERO_TEAM_ID", TEAM)
    monkeypatch.setattr(config_rag, "ZOTERO_GROUP_ID", 1)
    monkeypatch.setattr(config_rag, "ZOTERO_API_KEY", "test-key")
    monkeypatch.setattr(repo, "provider_for", lambda team_id: fake.provider())
    for name in ("add_paper", "delete_paper", "paper_chunk_counts", "paper_ids_with_meta", "drop_team", "reload"):
        monkeypatch.setattr(ingest.store, name, getattr(fake_store, name))
    monkeypatch.setattr(migrate_seed, "check_page_image", lambda team_id, paper_id: True)
    repo.reset_state()
    ingest.reset_state()
    yield SimpleEnv(seed_dir, index_dir, pdf_dir, fake, fake_store)
    repo.reset_state()
    ingest.reset_state()


class SimpleEnv:
    def __init__(self, seed_dir, index_dir, pdf_dir, fake, store):
        self.seed_dir, self.index_dir, self.pdf_dir, self.fake, self.store = seed_dir, index_dir, pdf_dir, fake, store
        self.out = []

    def say(self, text=""):
        self.out.append(str(text))

    def run(self, apply):
        return asyncio.run(migrate_seed.migrate(self.seed_dir, TEAM, apply, self.say))

    @property
    def text(self):
        return "\n".join(self.out)


def add_manual_adapter(env, same_pdf=True, title=None):
    """Zotero 앱에서 직접 넣은 Adapter 논문 (arXiv:ID [분류] 표기, 사람이 붙인 PDF 파일명)."""
    seed_pdf = next(env.seed_dir.glob("1902.00751*.pdf")).read_bytes()
    env.fake.adapter()
    data = env.fake.items["V3HSB2SA"]["data"]
    data["title"] = title or TITLES["1902.00751"]
    env.fake.items["8XQJP5SB"]["data"]["md5"] = hashlib.md5(seed_pdf if same_pdf else b"other").hexdigest()
    env.fake.files["8XQJP5SB"] = seed_pdf


def test_load_seeds_uses_only_listed_files(env):
    (env.seed_dir / "9999.99999v1_unknown.pdf").write_bytes(make_pdf())
    (env.seed_dir / "notes.txt").write_text("x")
    seeds = migrate_seed.load_seeds(env.seed_dir)
    assert sorted(s.arxiv_id for s in seeds) == sorted(SEED_FILES)  # 목록에 없는 PDF와 다른 확장자는 무시
    assert all(s.old_paper_id in {1, 2, 3, 4, 5} and s.version == SEED_FILES[s.arxiv_id][0] for s in seeds)
    candidate = next(s for s in seeds if s.arxiv_id == "2106.09685").candidate()
    assert (candidate.version, candidate.title.startswith("LoRA"), candidate.abstract, len(candidate.authors)) == ("v2", True, "", 8)


def test_dry_run_plans_but_writes_nothing(env):
    add_manual_adapter(env)
    before_items = len(env.fake.items)
    assert env.run(apply=False) is True
    assert "그대로 사용" in env.text and env.text.count("새로 등록") == 4 and "(dry-run)" in env.text
    assert len(env.fake.items) == before_items and env.fake.uploads == [] and env.fake.collections == []
    assert (env.index_dir / str(TEAM) / "meta.json").read_text() == "OLD INDEX" and not (env.index_dir.parent / "local_index_backup").exists()
    assert env.store.counts == {1: 65, 2: 67, 3: 76, 4: 112, 5: 106}


def test_plan_distinguishes_reuse_attach_create_and_warns_on_title(env):
    add_manual_adapter(env, same_pdf=False, title="내가 고친 제목")
    seeds = migrate_seed.load_seeds(env.seed_dir)
    papers, attachments = asyncio.run(migrate_seed._library())
    plan = {e["seed"].arxiv_id: e for e in migrate_seed.plan_for(seeds, papers, attachments)}
    assert plan["1902.00751"]["action"] == "attach" and plan["1902.00751"]["zotero_key"] == "V3HSB2SA"
    assert "제목이 시드 제목과 다릅니다" in plan["1902.00751"]["warnings"][0]
    assert all(plan[i]["action"] == "create" for i in SEED_FILES if i != "1902.00751")
    env.fake.items.clear()
    add_manual_adapter(env)
    papers, attachments = asyncio.run(migrate_seed._library())
    assert {e["seed"].arxiv_id: e["action"] for e in migrate_seed.plan_for(seeds, papers, attachments)}["1902.00751"] == "reuse"


def test_duplicate_zotero_items_stop_the_migration(env):
    add_manual_adapter(env)
    env.fake.add("DUPLIC01", itemType="preprint", title="Adapter again", extra="arXiv: 1902.00751")
    assert env.run(apply=True) is False
    assert "중복된 Zotero 항목" in env.text and not (env.index_dir.parent / "local_index_backup").exists()
    assert env.store.counts == {1: 65, 2: 67, 3: 76, 4: 112, 5: 106}


def test_apply_registers_missing_papers_and_rebuilds_the_index_from_zotero(env):
    add_manual_adapter(env)
    assert env.run(apply=True) is True, env.text
    papers = [i for i in env.fake.items.values() if i["data"].get("itemType") == "preprint"]
    assert len(papers) == 5  # Adapter는 새로 만들지 않고 직접 넣은 항목을 그대로 쓴다
    assert env.fake.items["V3HSB2SA"]["data"]["title"] == TITLES["1902.00751"]  # 사용자 항목은 덮어쓰지 않는다
    assert len(env.fake.uploads) == 4  # Adapter PDF는 같아서 올리지 않았다
    assert set(env.store.counts) == {paper_id_from_key(p["key"]) for p in papers}  # 새 id로 다시 만들어졌다
    assert not set(env.store.counts) & {1, 2, 3, 4, 5}
    assert all(m["zotero_key"] and m["source"] for m in env.store.metas.values())
    backups = list((env.index_dir.parent / "local_index_backup").iterdir())
    assert len(backups) == 1 and (backups[0] / "index" / "meta.json").read_text() == "OLD INDEX"
    assert (backups[0] / "pdfs" / "1.pdf").read_bytes() == b"OLD PDF"
    assert "청크 수가 다릅니다" in env.text  # 가짜 색인은 항상 3청크라 이전(65 등)과 다르다 -> 경고만 하고 통과한다
    assert "검증 통과" in env.text


def test_rerun_after_success_registers_nothing_twice(env):
    add_manual_adapter(env)
    assert env.run(apply=True) is True
    uploads, items = len(env.fake.uploads), len(env.fake.items)
    assert env.run(apply=True) is True
    assert len(env.fake.uploads) == uploads and len(env.fake.items) == items  # 같은 PDF가 이미 있어 아무것도 새로 만들지 않는다


def test_zotero_failure_leaves_the_index_untouched(env):
    add_manual_adapter(env)
    env.fake.storage_fail = True  # 새 논문의 PDF 업로드가 실패하는 상황
    with pytest.raises(Exception):
        env.run(apply=True)
    assert env.store.counts == {1: 65, 2: 67, 3: 76, 4: 112, 5: 106}  # 색인 비우기 전에 멈췄다
    assert (env.index_dir / str(TEAM) / "meta.json").read_text() == "OLD INDEX"


def test_index_failure_restores_the_backup(env, monkeypatch):
    add_manual_adapter(env)
    # 새 색인에서 한 편이 스캔 PDF로 실패하는 상황: 시드 중 하나의 PDF를 SCAN 바이트로 바꿔 둔다
    target = next(env.seed_dir.glob("2305.14314*.pdf"))
    target.write_bytes(SCAN)
    assert env.run(apply=True) is False
    assert "백업에서 색인을 복구했습니다" in env.text and "색인되지 않았습니다" in env.text
    assert (env.index_dir / str(TEAM) / "meta.json").read_text() == "OLD INDEX"  # 디스크의 색인·PDF가 원래대로 돌아왔다
    assert (env.pdf_dir / str(TEAM) / "1.pdf").read_bytes() == b"OLD PDF"


def test_page_image_failure_restores_the_backup(env, monkeypatch):
    add_manual_adapter(env)
    monkeypatch.setattr(migrate_seed, "check_page_image", lambda team_id, paper_id: False)
    assert env.run(apply=True) is False
    assert "페이지를 이미지로 만들 수 없습니다" in env.text and (env.index_dir / str(TEAM) / "meta.json").read_text() == "OLD INDEX"
