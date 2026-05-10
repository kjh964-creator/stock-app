"""
stock_archive.py — 종목 보관함 + 사용자 정의 폴더

저장: data/archive.json (기존 archive.json 확장)
구조:
{
  "folders": ["기본", "장기투자", "단기"],
  "items": [
    {"ticker": "005930", "name": "삼성전자", "folder": "기본", "added_at": "..."}
  ]
}

기존 list 형식 archive.json도 자동 마이그레이션.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
ARCHIVE_PATH = DATA_DIR / "archive.json"

DEFAULT_FOLDER = "기본"
PROTECTED_FOLDERS = {"기본"}


def _load() -> dict:
    if not ARCHIVE_PATH.exists():
        return {"folders": [DEFAULT_FOLDER], "items": []}
    try:
        data = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"folders": [DEFAULT_FOLDER], "items": []}

    # 기존 형식 (list) → 새 형식 마이그레이션
    if isinstance(data, list):
        items = []
        for it in data:
            it["folder"] = DEFAULT_FOLDER
            items.append(it)
        return {"folders": [DEFAULT_FOLDER], "items": items}
    if "folders" not in data:
        data["folders"] = [DEFAULT_FOLDER]
    if "items" not in data:
        data["items"] = []
    return data


def _save(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── 폴더 관리 ───
def get_folders() -> list[str]:
    data = _load()
    folders = data.get("folders", [DEFAULT_FOLDER])
    if DEFAULT_FOLDER not in folders:
        folders.insert(0, DEFAULT_FOLDER)
    return folders


def add_folder(name: str) -> tuple[bool, str]:
    name = name.strip()
    if not name:
        return False, "이름이 비어있어요"
    if len(name) > 30:
        return False, "30자 이하"
    data = _load()
    if name in data["folders"]:
        return False, f"'{name}' 이미 있어요"
    data["folders"].append(name)
    _save(data)
    return True, f"'{name}' 추가됨"


def remove_folder(name: str) -> tuple[bool, str]:
    if name in PROTECTED_FOLDERS:
        return False, f"'{name}'는 기본 폴더라 삭제 불가"
    data = _load()
    if name not in data["folders"]:
        return False, "그런 폴더 없어요"
    moved = 0
    for it in data["items"]:
        if it.get("folder") == name:
            it["folder"] = DEFAULT_FOLDER
            moved += 1
    data["folders"].remove(name)
    _save(data)
    msg = f"'{name}' 삭제됨"
    if moved:
        msg += f" (안의 {moved}개 → '기본'으로)"
    return True, msg


def count_in_folder(name: str) -> int:
    return sum(1 for it in _load()["items"] if it.get("folder") == name)


# ─── 종목 추가/이동/제거 ───
def add_stock(ticker: str, name: str, folder: str = DEFAULT_FOLDER) -> bool:
    data = _load()
    if folder not in data["folders"]:
        data["folders"].append(folder)
    for it in data["items"]:
        if it.get("ticker") == ticker:
            # 이미 있으면 폴더만 업데이트
            it["folder"] = folder
            _save(data)
            return False  # 신규 아님
    data["items"].append({
        "ticker": ticker,
        "name": name,
        "folder": folder,
        "added_at": datetime.now().isoformat(),
    })
    _save(data)
    return True


def move_stock(ticker: str, target_folder: str):
    data = _load()
    if target_folder not in data["folders"]:
        data["folders"].append(target_folder)
    for it in data["items"]:
        if it.get("ticker") == ticker:
            it["folder"] = target_folder
            break
    _save(data)


def remove_stock(ticker: str):
    data = _load()
    data["items"] = [i for i in data["items"] if i.get("ticker") != ticker]
    _save(data)


def get_stocks_in_folder(folder: str) -> list[dict]:
    data = _load()
    return [i for i in data["items"] if i.get("folder", DEFAULT_FOLDER) == folder]


def get_all_stocks() -> list[dict]:
    return _load()["items"]
