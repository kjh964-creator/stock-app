"""
user_input.py — 사용자가 입력한 정보(유튜브/URL/텍스트)를 Claude로 분석

app.py의 "📥 새 정보" 탭에서 사용.
"""

from __future__ import annotations

import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import anthropic

load_dotenv()

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
USER_INPUTS_PATH = DATA_DIR / "user_inputs.json"

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL_INPUT = "claude-sonnet-4-6"  # 사용자 입력 분석은 좀 더 똑똑한 모델

WATCHLIST_PATH = PROJECT_ROOT / "watchlist.csv"

NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


# ─────────────────────────────────────────────────────────────────────
# 유튜브 처리
# ─────────────────────────────────────────────────────────────────────
def extract_youtube_id(url: str) -> Optional[str]:
    """유튜브 URL에서 영상 ID 추출."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([\w-]{11})",
        r"youtube\.com/shorts/([\w-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_youtube_transcript(video_id: str, lang_priority: list[str] = None) -> Optional[str]:
    """유튜브 영상 자막 추출. youtube-transcript-api 사용."""
    lang_priority = lang_priority or ["ko", "en", "ja"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        # 한국어 자막 우선
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            for lang in lang_priority:
                try:
                    t = transcript_list.find_transcript([lang]).fetch()
                    return " ".join([entry["text"] for entry in t])
                except Exception:
                    continue
            # 자동 생성 자막이라도
            for tr in transcript_list:
                t = tr.fetch()
                return " ".join([entry["text"] for entry in t])
        except Exception:
            # 단순 방식 시도
            t = YouTubeTranscriptApi.get_transcript(video_id, languages=lang_priority)
            return " ".join([entry["text"] for entry in t])
    except ImportError:
        return None
    except Exception as e:
        print(f"[transcript] {e}")
        return None


def get_youtube_metadata(video_id: str) -> dict:
    """유튜브 영상 제목·설명 (oEmbed 사용 — API 키 불필요)."""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        r = requests.get(url, headers=NAVER_HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return {
                "title": data.get("title", ""),
                "author": data.get("author_name", ""),
                "thumbnail": data.get("thumbnail_url", ""),
            }
    except Exception:
        pass
    return {"title": "", "author": "", "thumbnail": ""}


# ─────────────────────────────────────────────────────────────────────
# 일반 URL 처리
# ─────────────────────────────────────────────────────────────────────
def fetch_url_text(url: str, max_chars: int = 6000) -> dict:
    """URL에서 본문 텍스트 추출."""
    try:
        r = requests.get(url, headers=NAVER_HEADERS, timeout=15)
        r.raise_for_status()
        # 인코딩 자동 감지
        if r.encoding == "ISO-8859-1":
            r.encoding = r.apparent_encoding

        soup = BeautifulSoup(r.text, "html.parser")
        # 노이즈 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        # 제목
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        # OG 메타도 확인
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"]

        # 본문
        article = soup.find("article") or soup.find("main") or soup.find(id=re.compile(r"content|article|main"))
        if article:
            text = article.get_text("\n", strip=True)
        else:
            text = soup.get_text("\n", strip=True)

        # 너무 짧은 줄 제거
        lines = [l for l in text.split("\n") if len(l) > 15]
        text = "\n".join(lines)[:max_chars]

        return {"title": title, "text": text, "url": url}
    except Exception as e:
        return {"title": "", "text": "", "url": url, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────
# Claude 분석
# ─────────────────────────────────────────────────────────────────────
ANALYSIS_PROMPT = """김진호님이 다음 정보를 공유하시고 분석을 요청했습니다.

## 입력 정보
**종류**: {content_type}
**제목/출처**: {source}
**본문**:
{content}

## 김진호님의 관심종목 (참고)
{watchlist_context}

## 작성 지침
다음 형식으로 마크다운 응답을 작성해주세요. 친근한 톤으로, 김진호님의 관심종목과 연결지어서.

### 📌 핵심 요약 (3~5줄)
- 이 정보가 무엇에 관한 것인지
- 핵심 메시지/주장 정리

### 🎯 언급된 종목 / 관련 종목
표 형식: | 종목명 | 티커 | 시사점 (🟢긍정/🟡중립/🔴부정) | 비고 |
- 김진호님의 관심종목 중에서 직접 언급되거나 영향받을 만한 것 우선
- 새로운 종목이 등장하면 [신규] 태그
- 티커 모르면 "—"

### 💡 김진호님께 드리는 의견
- 이 정보를 어떻게 해석해야 할지
- 추가로 알아볼 점 1~2개
- 관심종목 변화 추천 (있다면)

### 🏷️ 키워드 / 섹터 트렌드
관련 키워드 5~10개 (해시태그 형식)

마지막에 디스클레이머: "*투자 의견이 아닌 정보 정리입니다.*"
"""


def analyze_user_input(content: str, content_type: str = "텍스트",
                        source: str = "") -> dict:
    """사용자가 입력한 정보를 Claude로 분석.
    Returns: {"analysis": str, "related_tickers": list[str], "timestamp": iso}
    """
    if not ANTHROPIC_KEY:
        return {"error": "ANTHROPIC_API_KEY 미설정"}

    # watchlist 컨텍스트
    watchlist_context = "(watchlist.csv 없음)"
    try:
        import pandas as pd
        if WATCHLIST_PATH.exists():
            df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
            df = df.fillna({"ticker": ""})
            df["ticker"] = df["ticker"].str.zfill(6)
            df = df.drop_duplicates(subset=["ticker"])
            df = df[df["ticker"].str.strip() != ""]
            lines = [f"- {row['name']} ({row['ticker']})" for _, row in df.iterrows()]
            watchlist_context = "\n".join(lines)
    except Exception:
        pass

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = ANALYSIS_PROMPT.format(
        content_type=content_type,
        source=source or "(없음)",
        content=content[:8000],  # 너무 길면 자르기
        watchlist_context=watchlist_context,
    )

    response = client.messages.create(
        model=CLAUDE_MODEL_INPUT,
        max_tokens=3000,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )

    analysis_text = response.content[0].text

    # 응답에서 6자리 티커 추출 (간단한 정규식)
    related_tickers = list(set(re.findall(r"\b(\d{6})\b", analysis_text)))

    return {
        "analysis": analysis_text,
        "related_tickers": related_tickers,
        "timestamp": datetime.now().isoformat(),
        "content_type": content_type,
        "source": source,
        "model": CLAUDE_MODEL_INPUT,
    }


# ─────────────────────────────────────────────────────────────────────
# 영속화 (data/user_inputs.json 저장)
#   각 entry 의 status 필드:
#     "pending"  — 주식뉴스 탭에 표시 (기본값)
#     "archived" — 보관함 탭으로 이동
# ─────────────────────────────────────────────────────────────────────
def load_user_inputs() -> list[dict]:
    if USER_INPUTS_PATH.exists():
        try:
            return json.loads(USER_INPUTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_all(entries: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_INPUTS_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_user_input(entry: dict):
    """새 입력+분석 결과를 저장. 가장 최근이 맨 앞. status 기본값 'pending'."""
    if "status" not in entry:
        entry["status"] = "pending"
    entries = load_user_inputs()
    entries.insert(0, entry)
    entries = entries[:200]  # 최대 200개
    _save_all(entries)


def delete_user_input(entry_id: str):
    """⚠️ 영구 삭제. 휴지통 거치지 않음. 사용 시 주의."""
    entries = load_user_inputs()
    entries = [e for e in entries if e.get("id") != entry_id]
    _save_all(entries)


def trash_user_input(entry_id: str):
    """삭제 → 휴지통으로 (status='trashed')."""
    entries = load_user_inputs()
    for e in entries:
        if e.get("id") == entry_id:
            e["status"] = "trashed"
            e["trashed_at"] = datetime.now().isoformat()
            break
    _save_all(entries)


def archive_user_input(entry_id: str):
    """보관함으로 이동 (status='archived')."""
    entries = load_user_inputs()
    for e in entries:
        if e.get("id") == entry_id:
            e["status"] = "archived"
            e["archived_at"] = datetime.now().isoformat()
            break
    _save_all(entries)


def unarchive_user_input(entry_id: str):
    """보관 해제 → 다시 주식뉴스로."""
    entries = load_user_inputs()
    for e in entries:
        if e.get("id") == entry_id:
            e["status"] = "pending"
            e.pop("archived_at", None)
            e.pop("trashed_at", None)
            break
    _save_all(entries)


def restore_user_input(entry_id: str):
    """휴지통 → 다시 주식뉴스로 (=unarchive)."""
    unarchive_user_input(entry_id)


def get_pending_inputs() -> list[dict]:
    """주식뉴스 탭에 표시할 항목."""
    return [e for e in load_user_inputs() if e.get("status", "pending") == "pending"]


def get_archived_inputs() -> list[dict]:
    """정보 보관 탭에 표시할 항목."""
    return [e for e in load_user_inputs() if e.get("status") == "archived"]


def get_trashed_inputs() -> list[dict]:
    """휴지통 탭에 표시할 항목."""
    return [e for e in load_user_inputs() if e.get("status") == "trashed"]


# ─── 폴더 지원 (정보 보관용) ───
def get_archived_inputs_in_folder(folder: str = "기본") -> list[dict]:
    """특정 폴더의 정보 보관 항목."""
    return [
        e for e in load_user_inputs()
        if e.get("status") == "archived" and e.get("folder", "기본") == folder
    ]


def count_inputs_in_folder(folder: str) -> int:
    return sum(
        1 for e in load_user_inputs()
        if e.get("status") == "archived" and e.get("folder", "기본") == folder
    )


def move_user_input_to_folder(entry_id: str, folder: str):
    """정보를 다른 폴더로 이동 (status='archived' 유지)."""
    entries = load_user_inputs()
    for e in entries:
        if e.get("id") == entry_id:
            e["status"] = "archived"
            e["folder"] = folder
            if "archived_at" not in e:
                e["archived_at"] = datetime.now().isoformat()
            break
    _save_all(entries)


def _move_inputs_folder_to_default(folder: str) -> int:
    """폴더 삭제 시 안의 정보들을 기본으로 이동."""
    entries = load_user_inputs()
    count = 0
    for e in entries:
        if e.get("folder") == folder:
            e["folder"] = "기본"
            count += 1
    _save_all(entries)
    return count


def restore_all_trashed_inputs() -> int:
    """휴지통 정보 전부 복원 (status='pending'). 복원된 개수 반환."""
    entries = load_user_inputs()
    count = 0
    for e in entries:
        if e.get("status") == "trashed":
            e["status"] = "pending"
            e.pop("trashed_at", None)
            count += 1
    _save_all(entries)
    return count


def empty_inputs_trash() -> int:
    """휴지통 정보 전부 영구삭제. ⚠️ 복구 불가."""
    entries = load_user_inputs()
    before = len(entries)
    entries = [e for e in entries if e.get("status") != "trashed"]
    _save_all(entries)
    return before - len(entries)


# ─────────────────────────────────────────────────────────────────────
# 통합 처리 (app.py 에서 호출)
# ─────────────────────────────────────────────────────────────────────
def process_input(input_text: str, input_type: str = "auto") -> dict:
    """
    input_type: "auto" (URL 패턴 감지), "youtube", "url", "text"
    Returns: 저장된 entry dict
    """
    input_text = input_text.strip()
    if not input_text:
        return {"error": "입력 비어있음"}

    # auto 감지
    if input_type == "auto":
        if "youtube.com" in input_text or "youtu.be" in input_text:
            input_type = "youtube"
        elif input_text.startswith("http"):
            input_type = "url"
        else:
            input_type = "text"

    content = ""
    source = input_text

    if input_type == "youtube":
        video_id = extract_youtube_id(input_text)
        if not video_id:
            return {"error": "유튜브 ID를 찾을 수 없습니다"}

        meta = get_youtube_metadata(video_id)
        title = meta.get("title", "")
        author = meta.get("author", "")
        source = f"YouTube — {title} ({author})"

        transcript = get_youtube_transcript(video_id)
        if transcript:
            content = f"[영상 제목] {title}\n[채널] {author}\n\n[자막]\n{transcript}"
        else:
            content = f"[영상 제목] {title}\n[채널] {author}\n\n(자막 추출 실패. 제목·채널 기준으로만 분석)"

    elif input_type == "url":
        fetched = fetch_url_text(input_text)
        if fetched.get("error"):
            return {"error": f"URL 가져오기 실패: {fetched['error']}"}
        title = fetched.get("title", "")
        text = fetched.get("text", "")
        source = f"URL — {title or input_text}"
        content = f"[제목] {title}\n[URL] {input_text}\n\n[본문]\n{text}"

    else:  # text
        source = "직접 입력"
        content = input_text

    if not content:
        return {"error": "분석할 내용이 비어있습니다"}

    # Claude 분석
    result = analyze_user_input(content, content_type=input_type, source=source)
    if "error" in result:
        return result

    # entry 구성
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "input_text": input_text,
        "input_type": input_type,
        "source": source,
        "content_excerpt": content[:500],
        **result,
    }
    save_user_input(entry)
    return entry
