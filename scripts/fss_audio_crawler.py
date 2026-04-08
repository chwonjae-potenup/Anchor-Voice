#!/usr/bin/env python3
"""
금감원(FSS) 보이스피싱 음원 게시판 Selenium 크롤러.

목표(MVP):
1) 목록 페이지(1~23)를 순회
2) 상세 페이지 링크 추출
3) 상세 페이지 내 플레이어/다운로드 링크에서 음원 URL 탐지
4) requests로 파일 저장

지원 게시판:
- B0000206: 대출사기형
- B0000207: 수사기관 사칭형
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT = 15
DEFAULT_DELAY = 0.7


@dataclass(frozen=True)
class BoardConfig:
    key: str
    label: str
    board_id: str
    menu_no: str

    @property
    def list_url(self) -> str:
        return f"https://www.fss.or.kr/fss/bbs/{self.board_id}/list.do?menuNo={self.menu_no}"

    @property
    def view_url(self) -> str:
        return f"https://www.fss.or.kr/fss/bbs/{self.board_id}/view.do"


BOARD_MAP = {
    "loan": BoardConfig(
        key="loan",
        label="대출사기형",
        board_id="B0000206",
        menu_no="200690",
    ),
    "impersonation": BoardConfig(
        key="impersonation",
        label="수사기관 사칭형",
        board_id="B0000207",
        menu_no="200691",
    ),
}


def sanitize_filename(value: str, max_len: int = 180) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_len]


def detect_extension(url: str, content_type: str) -> str:
    path_ext = Path(urlparse(url).path).suffix.lower()
    if path_ext in {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".mp4"}:
        return path_ext

    ctype = (content_type or "").lower()
    if "audio/mpeg" in ctype or "audio/mp3" in ctype:
        return ".mp3"
    if "audio/wav" in ctype or "audio/x-wav" in ctype:
        return ".wav"
    if "audio/mp4" in ctype:
        return ".m4a"
    if "audio/ogg" in ctype:
        return ".ogg"
    if "video/mp4" in ctype:
        return ".mp4"
    return ".mp3"


def detect_extension_from_bytes(data: bytes) -> Optional[str]:
    if not data:
        return None
    # MP3: ID3 헤더 또는 프레임 sync(0xFFEx)
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return ".mp3"
    # WAV: RIFF....WAVE
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    # MP4/M4A: ....ftyp
    if len(data) >= 12 and data[4:8] == b"ftyp":
        major_brand = data[8:12]
        if major_brand in {b"M4A ", b"m4a ", b"isom", b"mp42", b"mp41"}:
            return ".m4a"
        return ".mp4"
    # OGG
    if data.startswith(b"OggS"):
        return ".ogg"
    return None


def extract_filename_from_cd(content_disposition: str) -> Optional[str]:
    if not content_disposition:
        return None
    match = re.search(r"filename\*=UTF-8''([^;\n]+)|filename=\"?([^\";]+)\"?", content_disposition, re.I)
    if not match:
        return None
    filename = match.group(1) or match.group(2)
    if not filename:
        return None
    return sanitize_filename(filename.strip().strip('"'))


def extract_extension_from_filename(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    ext = Path(filename).suffix.lower()
    if ext in {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".mp4"}:
        return ext
    return None


class FSSAudioCrawler:
    def __init__(
        self,
        out_root: Path,
        timeout: int = DEFAULT_TIMEOUT,
        delay: float = DEFAULT_DELAY,
        headless: bool = True,
        force: bool = False,
        driver_path: Optional[str] = None,
    ) -> None:
        self.out_root = out_root
        self.timeout = timeout
        self.delay = delay
        self.force = force
        self.out_root.mkdir(parents=True, exist_ok=True)

        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        self.driver = self.init_chrome_driver(options=options, driver_path=driver_path)

        self.wait = WebDriverWait(self.driver, self.timeout)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari/537.36",
                "Accept": "*/*",
            }
        )

    @staticmethod
    def init_chrome_driver(options: webdriver.ChromeOptions, driver_path: Optional[str]) -> webdriver.Chrome:
        """
        네트워크 차단 환경을 고려한 WebDriver 초기화.
        우선순위:
        1) --driver-path 인자
        2) CHROMEDRIVER 환경변수
        3) webdriver-manager 자동 설치
        4) Selenium 기본 탐색(로컬 PATH)
        """
        candidates: list[tuple[str, Optional[str]]] = [
            ("CLI driver_path", driver_path),
            ("ENV CHROMEDRIVER", os.environ.get("CHROMEDRIVER")),
        ]

        for source, path in candidates:
            if not path:
                continue
            path_obj = Path(path)
            if not path_obj.exists():
                logger.warning("%s 경로가 존재하지 않습니다: %s", source, path)
                continue
            try:
                logger.info("%s 사용: %s", source, path_obj)
                return webdriver.Chrome(service=ChromeService(str(path_obj)), options=options)
            except WebDriverException as exc:
                logger.warning("%s 초기화 실패: %s", source, exc)

        try:
            logger.info("webdriver-manager로 ChromeDriver 설치 시도")
            return webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=options,
            )
        except Exception as exc:
            logger.warning("webdriver-manager 초기화 실패(오프라인 가능): %s", exc)

        try:
            logger.info("Selenium 기본 ChromeDriver 탐색 시도")
            return webdriver.Chrome(options=options)
        except Exception as exc:
            logger.error(
                "Chrome WebDriver 초기화 실패. --driver-path 또는 CHROMEDRIVER 환경변수로 로컬 드라이버를 지정해 주세요. 상세: %s",
                exc,
            )
            raise

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass
        self.session.close()

    def run_board(self, board: BoardConfig, start_page: int, end_page: int) -> None:
        # 사용자 요구사항: 게시판 타입별 폴더를 한글 이름으로 분리
        board_dir = self.out_root / sanitize_filename(board.label.replace(" ", ""))
        board_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[%s] 페이지 %d~%d 수집 시작", board.label, start_page, end_page)

        for page in range(start_page, end_page + 1):
            list_url = f"{board.list_url}&pageIndex={page}"
            logger.info("[%s] 목록 페이지: %s", board.label, list_url)
            try:
                self.driver.get(list_url)
                self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except TimeoutException:
                logger.warning("[%s] 목록 페이지 로딩 타임아웃: %s", board.label, list_url)
                continue
            except Exception as exc:
                logger.warning("[%s] 목록 페이지 접근 실패: %s (%s)", board.label, list_url, exc)
                continue

            detail_targets = self.extract_detail_targets(board, list_url)
            if not detail_targets:
                logger.warning("[%s] 상세 링크를 찾지 못했습니다. page=%d", board.label, page)
                continue

            for detail_url, title_hint, ntt_id in detail_targets:
                logger.info("[%s] 상세 페이지: %s", board.label, detail_url)
                media_url = self.fetch_media_url(detail_url)
                if not media_url:
                    logger.info("[%s] 음원 URL 탐지 실패: %s", board.label, detail_url)
                    time.sleep(self.delay)
                    continue

                file_stem = self.make_file_stem(ntt_id=ntt_id, title_hint=title_hint, media_url=media_url)
                success = self.download_media(
                    media_url=media_url,
                    detail_url=detail_url,
                    out_dir=board_dir,
                    file_stem=file_stem,
                )
                if success:
                    logger.info("[%s] 저장 완료: %s", board.label, file_stem)
                time.sleep(self.delay)

        logger.info("[%s] 수집 완료", board.label)

    def extract_detail_targets(self, board: BoardConfig, list_url: str) -> list[tuple[str, str, str]]:
        """
        목록 페이지에서 상세 페이지 URL/제목/nttId 추출.
        - href가 javascript(...) 형태인 경우 nttId를 파싱하여 view.do URL로 복원
        """
        html = self.driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        targets: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        max_items_per_page = 10

        # 1차: 게시글 테이블 행 단위 추출 (가장 안전)
        for row in soup.select("table tbody tr"):
            anchor = row.select_one("td.title a[href]") or row.select_one("a[href]")
            if not anchor:
                continue

            title_hint = anchor.get_text(" ", strip=True) or "untitled"
            href = (anchor.get("href") or "").strip()
            onclick = (anchor.get("onclick") or "").strip()

            detail_url, ntt_id = self.resolve_detail_url(
                board=board,
                list_url=list_url,
                href=href,
                onclick=onclick,
            )
            # 상세 페이지로 보이는 링크만 허용
            if not detail_url:
                continue
            if not (ntt_id or f"/{board.board_id}/view.do" in detail_url):
                continue
            if detail_url in seen:
                continue

            seen.add(detail_url)
            targets.append((detail_url, title_hint, ntt_id))
            if len(targets) >= max_items_per_page:
                break

        # 2차 fallback: 테이블 파싱 실패 시에만 넓은 셀렉터 사용(그래도 10개 제한)
        if not targets:
            for anchor in soup.select("td.title a[href], .bbs_list a[href], a[href]"):
                title_hint = anchor.get_text(" ", strip=True) or "untitled"
                href = (anchor.get("href") or "").strip()
                onclick = (anchor.get("onclick") or "").strip()

                detail_url, ntt_id = self.resolve_detail_url(
                    board=board,
                    list_url=list_url,
                    href=href,
                    onclick=onclick,
                )
                if not detail_url:
                    continue
                if not (ntt_id or f"/{board.board_id}/view.do" in detail_url):
                    continue
                if detail_url in seen:
                    continue

                seen.add(detail_url)
                targets.append((detail_url, title_hint, ntt_id))
                if len(targets) >= max_items_per_page:
                    break

        logger.info("[%s] 페이지당 상세 타깃 %d개 추출", board.label, len(targets))
        return targets

    def resolve_detail_url(
        self,
        board: BoardConfig,
        list_url: str,
        href: str,
        onclick: str,
    ) -> tuple[Optional[str], str]:
        """
        상세 URL을 안전하게 복원.
        반환값: (url, ntt_id)
        """
        ntt_id = self.extract_ntt_id(href) or self.extract_ntt_id(onclick)

        if href and href.lower().startswith("javascript"):
            if ntt_id:
                return f"{board.view_url}?nttId={ntt_id}&menuNo={board.menu_no}", ntt_id
            return None, ""

        if href:
            absolute = urljoin(list_url, href)
            if f"/{board.board_id}/view.do" in absolute:
                parsed = urlparse(absolute)
                parsed_qs = parse_qs(parsed.query)
                if "nttId" in parsed_qs and parsed_qs["nttId"]:
                    ntt_id = parsed_qs["nttId"][0]
                return absolute, ntt_id or ""

        if ntt_id:
            return f"{board.view_url}?nttId={ntt_id}&menuNo={board.menu_no}", ntt_id
        return None, ""

    @staticmethod
    def extract_ntt_id(text: str) -> Optional[str]:
        if not text:
            return None
        # nttId=12345 또는 fn_view('12345') 류 처리
        patterns = [
            r"nttId=(\d+)",
            r"\((?:'|\")?(\d+)(?:'|\")?\)",
            r",\s*(?:'|\")?(\d+)(?:'|\")?\s*\)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def fetch_media_url(self, detail_url: str) -> Optional[str]:
        """
        상세 페이지에서 음원 URL 탐지.
        탐지 순서:
        1) <audio>/<video>/<source> src
        2) page_source 정규식(fileDown.do, 확장자 URL)
        3) Selenium 성능 로그(response URL) 기반 탐지
        """
        try:
            self.driver.get(detail_url)
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except TimeoutException:
            logger.warning("상세 페이지 타임아웃: %s", detail_url)
            return None
        except Exception as exc:
            logger.warning("상세 페이지 접근 실패: %s (%s)", detail_url, exc)
            return None

        # 성능 로그를 비워 현재 페이지 이벤트만 취급
        self.safe_drain_performance_logs()

        # 플레이 버튼/더보기 버튼 등 클릭 시도 (실패해도 계속 진행)
        self.try_interactions_for_player()
        time.sleep(0.6)

        candidates = self.collect_media_candidates(detail_url)
        if candidates:
            return candidates[0]
        return None

    def safe_drain_performance_logs(self) -> None:
        try:
            _ = self.driver.get_log("performance")
        except Exception:
            pass

    def try_interactions_for_player(self) -> None:
        selectors = [
            "button[class*='play']",
            "a[class*='play']",
            "div[class*='play']",
            "button[aria-label*='재생']",
            "button[title*='재생']",
            "button[class*='more']",
            "button[class*='menu']",
            "div[class*='more']",
        ]
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements[:2]:
                    if not element.is_displayed():
                        continue
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        time.sleep(0.2)
                    except Exception:
                        continue
            except Exception:
                continue

    def collect_media_candidates(self, detail_url: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()

        def add(url: Optional[str]) -> None:
            if not url:
                return
            normalized = urljoin(detail_url, url.strip())
            if not normalized or normalized in seen:
                return
            if "javascript:" in normalized.lower():
                return
            seen.add(normalized)
            found.append(normalized)

        # 1) DOM에서 src 속성 수집
        try:
            urls_from_dom = self.driver.execute_script(
                """
                const out = [];
                const mediaEls = document.querySelectorAll('audio, video, source');
                mediaEls.forEach(el => {
                  if (el.currentSrc) out.push(el.currentSrc);
                  if (el.src) out.push(el.src);
                });
                const srcEls = document.querySelectorAll('[data-src], [data-url], [href]');
                srcEls.forEach(el => {
                  const v = el.getAttribute('data-src') || el.getAttribute('data-url') || el.getAttribute('href');
                  if (v) out.push(v);
                });
                return out;
                """
            )
            for url in urls_from_dom or []:
                add(url)
        except Exception:
            pass

        # 2) 페이지 HTML에서 URL 패턴 탐지
        html = self.driver.page_source
        for match in re.findall(r"(?:https?:)?//[^\s'\"<>]+", html):
            if self.looks_like_media_url(match):
                add(match)
        for match in re.findall(r"(?:/[^'\"<>\s]+fileDown\.do[^'\"<>\s]*)", html):
            add(match)

        # 3) 성능 로그에서 네트워크 응답 URL 추출
        for url in self.get_media_urls_from_performance_logs():
            add(url)

        # 우선순위: fileDown.do > 오디오 확장자 > 기타 media
        def score(url: str) -> tuple[int, int]:
            lower = url.lower()
            if "filedown.do" in lower:
                return (0, len(url))
            if re.search(r"\.(mp3|wav|m4a|ogg|aac|mp4)(\?|$)", lower):
                return (1, len(url))
            return (2, len(url))

        found.sort(key=score)
        return found

    def get_media_urls_from_performance_logs(self) -> list[str]:
        urls: list[str] = []
        try:
            logs = self.driver.get_log("performance")
        except Exception:
            return urls

        for entry in logs:
            try:
                payload = json.loads(entry["message"])
                msg = payload.get("message", {})
                if msg.get("method") != "Network.responseReceived":
                    continue
                response = msg.get("params", {}).get("response", {})
                url = response.get("url")
                mime = (response.get("mimeType") or "").lower()
                if not url:
                    continue
                if self.looks_like_media_url(url) or mime.startswith("audio/") or "video/" in mime:
                    urls.append(url)
            except Exception:
                continue
        return urls

    @staticmethod
    def looks_like_media_url(url: str) -> bool:
        lower = (url or "").lower()
        return (
            "filedown.do" in lower
            or bool(re.search(r"\.(mp3|wav|m4a|ogg|aac|mp4)(\?|$)", lower))
            or "audio" in lower
        )

    def make_file_stem(self, ntt_id: str, title_hint: str, media_url: str) -> str:
        # 사용자 요구사항: 파일명은 게시물 제목 우선
        title = sanitize_filename(title_hint or "untitled")
        if title and title != "untitled":
            return title
        # 제목을 가져오지 못한 예외 케이스에만 보조 식별자 사용
        if ntt_id:
            return f"ntt{ntt_id}"
        digest = hashlib.md5(media_url.encode("utf-8")).hexdigest()[:8]
        return f"audio_{digest}"

    @staticmethod
    def resolve_unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 2
        while True:
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def download_media(self, media_url: str, detail_url: str, out_dir: Path, file_stem: str) -> bool:
        headers = {"Referer": detail_url}
        try:
            with self.session.get(
                media_url,
                headers=headers,
                stream=True,
                timeout=self.timeout,
                allow_redirects=True,
            ) as response:
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type.lower():
                    logger.warning("HTML 응답 수신(다운로드 실패 가능): %s", media_url)
                    return False

                cd_name = extract_filename_from_cd(response.headers.get("content-disposition", ""))
                cd_ext = extract_extension_from_filename(cd_name)
                first_chunk = next(response.iter_content(chunk_size=8192), b"")
                magic_ext = detect_extension_from_bytes(first_chunk)
                ext = (
                    detect_extension(response.url or media_url, content_type)
                    or cd_ext
                    or magic_ext
                    or ".mp3"
                )
                # URL/Content-Type 추론이 약한 경우를 대비해 보정
                if ext == ".mp3" and cd_ext:
                    ext = cd_ext
                if ext == ".mp3" and magic_ext:
                    ext = magic_ext

                # 사용자 요구사항: 파일명은 항상 게시물 제목 기반으로 고정
                filename = sanitize_filename(file_stem) + ext

                out_path = out_dir / filename
                if out_path.exists():
                    if self.force:
                        logger.info("기존 파일 덮어쓰기: %s", out_path)
                    else:
                        out_path = self.resolve_unique_path(out_path)
                        logger.info("동일 제목 파일 존재로 새 이름 사용: %s", out_path.name)

                with open(out_path, "wb") as fp:
                    if first_chunk:
                        fp.write(first_chunk)
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            fp.write(chunk)
                return True
        except requests.RequestException as exc:
            logger.warning("다운로드 실패: %s (%s)", media_url, exc)
            return False
        except Exception as exc:
            logger.warning("파일 저장 실패: %s (%s)", media_url, exc)
            return False


def parse_boards(raw: str) -> list[BoardConfig]:
    keys = [k.strip().lower() for k in raw.split(",") if k.strip()]
    boards: list[BoardConfig] = []
    for key in keys:
        if key not in BOARD_MAP:
            valid = ", ".join(BOARD_MAP.keys())
            raise ValueError(f"지원하지 않는 boards 값: {key} (지원: {valid})")
        boards.append(BOARD_MAP[key])
    return boards


def run(
    boards: Iterable[BoardConfig],
    start: int,
    end: int,
    out_dir: Path,
    headless: bool,
    force: bool,
    driver_path: Optional[str],
) -> None:
    crawler = FSSAudioCrawler(
        out_root=out_dir,
        headless=headless,
        force=force,
        driver_path=driver_path,
    )
    try:
        for board in boards:
            crawler.run_board(board, start_page=start, end_page=end)
    finally:
        crawler.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="금감원 보이스피싱 음원 Selenium 크롤러")
    parser.add_argument(
        "--boards",
        default="loan,impersonation",
        help="수집 대상 게시판: loan, impersonation (쉼표로 복수 지정 가능)",
    )
    parser.add_argument("--start", type=int, default=1, help="시작 페이지")
    parser.add_argument("--end", type=int, default=23, help="종료 페이지")
    parser.add_argument("--out", default="downloads/fss_audio", help="저장 루트 디렉터리")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="헤드리스 모드 사용(기본: False, UI 보면서 디버깅 가능)",
    )
    parser.add_argument("--force", action="store_true", help="같은 파일명 존재 시 덮어쓰기")
    parser.add_argument(
        "--driver-path",
        default=None,
        help="로컬 chromedriver 실행 파일 경로(오프라인 환경 대응)",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.start < 1 or args.end < args.start:
        raise ValueError("--start/--end 값이 올바르지 않습니다.")

    boards = parse_boards(args.boards)
    out_dir = Path(args.out).resolve()
    logger.info("저장 경로: %s", out_dir)
    logger.info("대상 게시판: %s", ", ".join(board.label for board in boards))

    run(
        boards=boards,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
        headless=args.headless,
        force=args.force,
        driver_path=args.driver_path,
    )


if __name__ == "__main__":
    main()
