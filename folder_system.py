"""
folder_system.py — 통합 폴더 관리

종목 보관, 뉴스 보관, 정보 보관 모두 공유하는 폴더 시스템.
폴더 추가/삭제는 여기서 한 곳에만 — 각 모듈은 폴더명만 참조.

저장: data/folders_global.json
{
  "folders": ["기본", "장기투자", "단기", "공부자료", "흥미로운 뉴스"]
}
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
FOLDERS_PATH = DATA_DIR / "folders_global.json"

DEFAULT_FOLDER = "기본"
PROTECTED_FOLDERS = {"기본"}


def _load_raw() -> list[str]:
    """파일에서만 읽기."""
    if FOLDERS_PATH.exists():
        try:
            data = json.loads(FOLDERS_PATH.read_text(encoding="utf-8"))
            return data.get("folders", [])
        except Exception:
            pass
    return []


def _save(folders: list[str]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FOLDERS_PATH.write_text(
        json.dumps({"folders": folders}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _bootstrap_from_existing() -> list[str]:
    """기존 archive_manager + stock_archive 폴더로 초기화."""
    folders = {DEFAULT_FOLDER}
    try:
        from archive_manager import get_folders as get_news_folders
        for f in get_news_folders():
            folders.add(f)
    except Exception:
        pass
    try:
        from stock_archive import get_folders as get_stock_folders
        for f in get_stock_folders():
            folders.add(f)
    except Exception:
        pass
    return sorted(folders, key=lambda x: (x != DEFAULT_FOLDER, x))


def get_folders() -> list[str]:
    """글로벌 폴더 목록. 첫 호출 시 기존 모듈에서 자동 가져옴."""
    folders = _load_raw()
    if not folders:
        folders = _bootstrap_from_existing()
        _save(folders)
    if DEFAULT_FOLDER not in folders:
        folders.insert(0, DEFAULT_FOLDER)
    return folders


def add_folder(name: str) -> tuple[bool, str]:
    """폴더 추가. 양 모듈에도 동기화."""
    name = name.strip()
    if not name:
        return False, "이름이 비어있어요"
    if len(name) > 30:
        return False, "30자 이하"
    folders = get_folders()
    if name in folders:
        return False, f"'{name}' 이미 있음"
    folders.append(name)
    _save(folders)
    # 양 모듈에도 추가 (양방향 동기화)
    try:
        from archive_manager import add_folder as add_news_folder
        add_news_folder(name)
    except Exception:
        pass
    try:
        from stock_archive import add_folder as add_stock_folder
        add_stock_folder(name)
    except Exception:
        pass
    return True, f"'{name}' 추가됨"


def remove_folder(name: str) -> tuple[bool, str]:
    """폴더 제거. 안의 모든 종목/뉴스/정보는 '기본'으로 이동."""
    if name in PROTECTED_FOLDERS:
        return False, f"'{name}'는 기본 폴더라 삭제 불가"
    folders = get_folders()
    if name not in folders:
        return False, "그런 폴더 없어요"
    folders.remove(name)
    _save(folders)

    moved = 0
    # 뉴스
    try:
        from archive_manager import remove_folder as remove_news_folder
        remove_news_folder(name)
    except Exception:
        pass
    # 종목
    try:
        from stock_archive import remove_folder as remove_stock_folder
        remove_stock_folder(name)
    except Exception:
        pass
    # 정보
    try:
        from user_input import _move_inputs_folder_to_default
        moved += _move_inputs_folder_to_default(name)
    except Exception:
        pass

    return True, f"'{name}' 삭제됨"


def sync_all() -> None:
    """양 모듈에 글로벌 폴더 모두 추가 (없는 폴더 동기화)."""
    folders = get_folders()
    for f in folders:
        if f == DEFAULT_FOLDER:
            continue
        try:
            from archive_manager import add_folder as add_news
            add_news(f)
        except Exception:
            pass
        try:
            from stock_archive import add_folder as add_stock
            add_stock(f)
        except Exception:
            pass


def count_total(folder: str) -> tuple[int, int, int]:
    """선택 폴더의 (종목, 뉴스, 정보) 개수."""
    n_stocks = 0
    n_news = 0
    n_infos = 0
    try:
        from stock_archive import count_in_folder as count_stk
        n_stocks = count_stk(folder)
    except Exception:
        pass
    try:
        from archive_manager import count_in_folder as count_news
        n_news = count_news(folder)
    except Exception:
        pass
    try:
        from user_input import count_inputs_in_folder
        n_infos = count_inputs_in_folder(folder)
    except Exception:
        pass
    return n_stocks, n_news, n_infos
