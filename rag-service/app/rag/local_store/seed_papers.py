"""로컬 테스트용 시드 논문 목록 (DEV_03 3.7절 지정 5편, 버전 고정).

paper_id는 로컬 임시 값이다. 데이터 파트의 rag_papers.id와는 무관하다.
authors는 rag_papers.authors와 같은 쉼표 구분 문자열이며, 각 PDF 1쪽의 저자 표기로 확인했다.
"""
import re

SEED_PAPERS = {
    "1902.00751": {"paper_id": 1, "title": "Parameter-Efficient Transfer Learning for NLP", "year": 2019,
                   "authors": "Neil Houlsby, Andrei Giurgiu, Stanisław Jastrzębski, Bruna Morrone, Quentin de Laroussilhe, Andrea Gesmundo, Mona Attariyan, Sylvain Gelly"},
    "2101.00190": {"paper_id": 2, "title": "Prefix-Tuning: Optimizing Continuous Prompts for Generation", "year": 2021,
                   "authors": "Xiang Lisa Li, Percy Liang"},
    "2104.08691": {"paper_id": 3, "title": "The Power of Scale for Parameter-Efficient Prompt Tuning", "year": 2021,
                   "authors": "Brian Lester, Rami Al-Rfou, Noah Constant"},
    "2106.09685": {"paper_id": 4, "title": "LoRA: Low-Rank Adaptation of Large Language Models", "year": 2021,
                   "authors": "Edward J. Hu, Yelong Shen, Phillip Wallis, Zeyuan Allen-Zhu, Yuanzhi Li, Shean Wang, Lu Wang, Weizhu Chen"},
    "2305.14314": {"paper_id": 5, "title": "QLoRA: Efficient Finetuning of Quantized LLMs", "year": 2023,
                   "authors": "Tim Dettmers, Artidoro Pagnoni, Ari Holtzman, Luke Zettlemoyer"},
    # 분야별 일반화 점검용 비PEFT 논문 (색인에 섞어 쓴다, tags로 구분)
    "2206.15000": {"paper_id": 6, "title": "Grounded Copilot: How Programmers Interact with Code-Generating Models", "year": 2022, "tags": "hci",
                   "authors": "Shraddha Barke, Michael B. James, Nadia Polikarpova"},
    "2212.13138": {"paper_id": 7, "title": "Large Language Models Encode Clinical Knowledge", "year": 2022, "tags": "medical",
                   "authors": "Karan Singhal, Shekoofeh Azizi, Tao Tu, S. Sara Mahdavi, Jason Wei, Hyung Won Chung, Nathan Scales, Ajay Tanwani, Heather Cole-Lewis, Stephen Pfohl, Perry Payne, Martin Seneviratne, Paul Gamble, Chris Kelly, Nathaneal Schärli, Aakanksha Chowdhery, Philip Mansfield, Blaise Agüera y Arcas, Dale Webster, Greg S. Corrado, Yossi Matias, Katherine Chou, Juraj Gottweis, Nenad Tomasev, Yun Liu, Alvin Rajkomar, Joelle Barral, Christopher Semturs, Alan Karthikesalingam, Vivek Natarajan"},
    "2201.11903": {"paper_id": 8, "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models", "year": 2022, "tags": "prompting",
                   "authors": "Jason Wei, Xuezhi Wang, Dale Schuurmans, Maarten Bosma, Brian Ichter, Fei Xia, Ed H. Chi, Quoc V. Le, Denny Zhou"},
    "1706.03762": {"paper_id": 9, "title": "Attention Is All You Need", "year": 2017, "tags": "transformer",
                   "authors": "Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Łukasz Kaiser, Illia Polosukhin"},
}

_FILE_RE = re.compile(r"^(\d{4}\.\d{4,5})v(\d+)_")


def identify(filename: str) -> dict | None:
    """파일명(예: 2106.09685v2_lora.pdf)에서 논문 정보를 찾는다. 목록에 없으면 None."""
    m = _FILE_RE.match(filename)
    if not m or m.group(1) not in SEED_PAPERS:
        return None
    arxiv_id = m.group(1)
    return {**SEED_PAPERS[arxiv_id], "arxiv_id": arxiv_id, "version": f"v{m.group(2)}",
            "url": f"https://arxiv.org/abs/{arxiv_id}"}
