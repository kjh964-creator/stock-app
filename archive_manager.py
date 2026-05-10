"""
archive_manager.py — 뉴스 보관함 + 삭제함 (휴지통) + 사용자 정의 폴더

저장 위치: data/news_archive.json
구조:
{
  "folders": ["기본", "흥미로운 뉴스", "공부 자료"],
  "items": [
    {
      "id": "news_20260510143025_abc123",
      "folder": "기본",
      "status": "active" | "trashed",         <- 휴지통이면 trashed
      "title": "...",
      "link": "...",
      "summary": "...",
      "ticker": "005930",
      "stock_name": "삼성전자",
      "archived_at": "2026-05-10T14:30:25",
      "trashed_at": "2026-05-10T15:00:00"  <- 휴지통 이동 시각
    },
    ...
  ]
}

dedup: 새 뉴스 가져올 때 이미 archive(active+trashed) 에 있는 title 은 제외.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
NEWS_ARCHIVE_PATH = DATA_DIR / "news_archive.json"

DEFAULT_FOLDER = "기본"
PROTECTED_FOLDERS = {"기본"}


def _load() -> dict:
    if NEWS_ARCHIVE_PATH.exists():
        try:
            return json.loads(NEWS_ARCHIVE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"folders": [DEFAULT_FOLDER], "items": []}


def _save(data: dict):
    NEWS_ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NEWS_ARCHIVE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_status(item: dict) -> str:
    """과거 데이터 호환: status 없으면 active 로 간주."""
    return item.get("status", "active")


# ─────────────────────────────────────────────────────────────────────
# 폴더 관리
# ─────────────────────────────────────────────────────────────────────
def get_folders() -> list[str]:
    data = _load()
    folders = data.get("folders", [DEFAULT_FOLDER])
    if DEFAULT_FOLDER not in folders:
        folders.insert(0, DEFAULT_FOLDER)
    return folders


def add_folder(name: str) -> tuple[bool, str]:
    name = name.strip()
    if not name:
        return False, "폴더 이름이 비어있어요"
    if len(name) > 30:
        return False, "폴더 이름은 30자 이하로"
    data = _load()
    if name in data["folders"]:
        return False, f"'{name}' 폴더는 이미 있어요"
    data["folders"].append(name)
    _save(data)
    return True, f"'{name}' 폴더 생성됨"


def remove_folder(name: str) -> tuple[bool, str]:
    if name in PROTECTED_FOLDERS:
        return False, f"'{name}'는 기본 폴더라 삭제 불가"
    data = _load()
    if name not in data["folders"]:
        return False, "그런 폴더 없어요"

    moved = 0
    for item in data["items"]:
        if item.get("folder") == name and _get_status(item) == "active":
            item["folder"] = DEFAULT_FOLDER
            moved += 1

    data["folders"].remove(name)
    _save(data)
    msg = f"'{name}' 폴더 삭제됨"
    if moved:
        msg += f" (안에 있던 {moved}개는 '기본'으로 이동)"
    return True, msg


def rename_folder(old: str, new: str) -> tuple[bool, str]:
    if old in PROTECTED_FOLDERS:
        return False, f"'{old}'는 기본 폴더라 이름 변경 불가"
    new = new.strip()
    if not new or new == old:
        return False, "유효하지 않은 이름"
    data = _load()
    if old not in data["folders"]:
        return False, "그런 폴더 없어요"
    if new in data["folders"]:
        return False, f"'{new}' 이름은 이미 있어요"
    idx = data["folders"].index(old)
    data["folders"][idx] = new
    for item in data["items"]:
        if item.get("folder") == old:
            item["folder"] = new
    _save(data)
    return True, f"'{old}' → '{new}'"


# ─────────────────────────────────────────────────────────────────────
# 뉴스 아이템 — 추가/이동/휴지통/복원/영구삭제
# ─────────────────────────────────────────────────────────────────────
def add_news(
    title: str,
    link: str = "",
    summary: str = "",
    ticker: str = "",
    stock_name: str = "",
    folder: str = DEFAULT_FOLDER,
) -> str:
    """뉴스 보관 (status=active). 같은 title 이 같은 폴더에 active 로 있으면 중복 안 만듦."""
    data = _load()
    if folder not in data["folders"]:
        data["folders"].append(folder)

    # 중복 체크 (active 상태로 같은 폴더에 같은 제목)
    for item in data["items"]:
        if (item.get("folder") == folder
                and item.get("title") == title
                and _get_status(item) == "active"):
            return item["id"]

    item_id = f"news_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    new_item = {
        "id": item_id,
        "folder": folder,
        "status": "active",
        "title": title,
        "link": link,
        "summary": summary,
        "ticker": ticker,
        "stock_name": stock_name,
        "archived_at": datetime.now().isoformat(),
    }
    data["items"].insert(0, new_item)
    _save(data)
    return item_id


def trash_news(item_id_or_dict, **kwargs) -> str:
    """휴지통으로 이동 (또는 새로 휴지통에 직접 추가).
    인자가 dict 면 새 아이템을 휴지통에 바로 추가 (중복 체크 후).
    """
    data = _load()

    if isinstance(item_id_or_dict, dict):
        # 새 아이템을 휴지통으로 직접 추가
        title = item_id_or_dict.get("title", "")
        # 중복 체크 (어떤 status 든)
        for item in data["items"]:
            if item.get("title") == title:
                # 이미 있으면 status 만 trashed 로
                item["status"] = "trashed"
                item["trashed_at"] = datetime.now().isoformat()
                _save(data)
                return item["id"]

        item_id = f"news_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        new_item = {
            "id": item_id,
            "folder": DEFAULT_FOLDER,
            "status": "trashed",
            "title": title,
            "link": item_id_or_dict.get("link", ""),
            "summary": item_id_or_dict.get("summary", ""),
            "ticker": item_id_or_dict.get("ticker", ""),
            "stock_name": item_id_or_dict.get("stock_name", ""),
            "archived_at": datetime.now().isoformat(),
            "trashed_at": datetime.now().isoformat(),
        }
        data["items"].insert(0, new_item)
        _save(data)
        return item_id

    # 기존 아이템을 휴지통으로
    item_id = item_id_or_dict
    for item in data["items"]:
        if item.get("id") == item_id:
            item["status"] = "trashed"
            item["trashed_at"] = datetime.now().isoformat()
            break
    _save(data)
    return item_id


def restore_news(item_id: str, target_folder: str = DEFAULT_FOLDER):
    """휴지통 → 활성 (지정 폴더로)."""
    data = _load()
    for item in data["items"]:
        if item.get("id") == item_id:
            item["status"] = "active"
            item["folder"] = target_folder
            item.pop("trashed_at", None)
            break
    _save(data)


def permanent_delete(item_id: str):
    """영구 삭제."""
    data = _load()
    data["items"] = [i for i in data["items"] if i.get("id") != item_id]
    _save(data)


def move_news(item_id: str, target_folder: str) -> bool:
    data = _load()
    if target_folder not in data["folders"]:
        data["folders"].append(target_folder)
    found = False
    for item in data["items"]:
        if item.get("id") == item_id:
            item["folder"] = target_folder
            found = True
            break
    if found:
        _save(data)
    return found


# ─────────────────────────────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────────────────────────────
def get_news_in_folder(folder: str) -> list[dict]:
    """선택된 폴더 안의 active 뉴스. 최근 보관순."""
    data = _load()
    items = [i for i in data["items"] if i.get("folder") == folder and _get_status(i) == "active"]
    items.sort(key=lambda x: x.get("archived_at", ""), reverse=True)
    return items


def get_trashed_news() -> list[dict]:
    """휴지통 안 뉴스. 최근 휴지통 이동순."""
    data = _load()
    items = [i for i in data["items"] if _get_status(i) == "trashed"]
    items.sort(key=lambda x: x.get("trashed_at", x.get("archived_at", "")), reverse=True)
    return items


def count_in_folder(folder: str) -> int:
    return sum(
        1 for i in _load()["items"]
        if i.get("folder") == folder and _get_status(i) == "active"
    )


def count_trashed() -> int:
    return sum(1 for i in _load()["items"] if _get_status(i) == "trashed")


def get_seen_titles() -> set[str]:
    """이미 처리(보관 OR 휴지통)된 뉴스 제목 집합. 새 뉴스 dedup 용."""
    data = _load()
    return {i.get("title", "") for i in data["items"]}


def empty_trash_older_than(days: int = 30) -> int:
    """N일 이상 된 휴지통 항목 영구 삭제. 삭제된 개수 반환."""
    data = _load()
    cutoff = datetime.now() - timedelta(days=days)
    before = len(data["items"])
    new_items = []
    for item in data["items"]:
        if _get_status(item) != "trashed":
            new_items.append(item)
            continue
        trashed_at = item.get("trashed_at", item.get("archived_at", ""))
        try:
            dt = datetime.fromisoformat(trashed_at)
            if dt < cutoff:
                continue  # 영구 삭제
        except Exception:
            pass
        new_items.append(item)
    data["items"] = new_items
    _save(data)
    return before - len(new_items)


def restore_all_trashed_news() -> int:
    """휴지통 뉴스 전부 복원 (기본 폴더로). 복원된 개수 반환."""
    data = _load()
    count = 0
    for item in data["items"]:
        if _get_status(item) == "trashed":
            item["status"] = "active"
            item["folder"] = item.get("folder") or DEFAULT_FOLDER
            item.pop("trashed_at", None)
            count += 1
    _save(data)
    return count


def empty_trash_all() -> int:
    """휴지통 전부 비우기 (영구삭제). ⚠️ 복구 불가."""
    data = _load()
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if _get_status(i) != "trashed"]
    _save(data)
    return before - len(data["items"])
