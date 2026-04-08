# FSS Audio Crawler

금감원 보이스피싱 음원 게시판(B0000206, B0000207)에서 음원을 수집하는 Selenium 기반 크롤러입니다.

## 대상 게시판

- `loan` (`B0000206`, menuNo=`200690`): 대출사기형 보이스피싱
- `impersonation` (`B0000207`, menuNo=`200691`): 수사기관 사칭형 보이스피싱

## 설치

```powershell
python -m pip install -r requirements.txt
```

## 실행 예시

```powershell
# 두 게시판 모두, 1~23페이지 수집
python scripts\fss_audio_crawler.py --boards loan,impersonation --start 1 --end 23 --headless

# 대출사기형만 1~3페이지 테스트
python scripts\fss_audio_crawler.py --boards loan --start 1 --end 3 --headless
```

## 주요 옵션

- `--boards`: `loan`, `impersonation` (쉼표로 복수 지정)
- `--start`, `--end`: 수집 페이지 범위
- `--out`: 저장 루트 경로 (기본 `downloads/fss_audio`)
- `--headless`: 브라우저 UI 없이 실행
- `--force`: 같은 파일명 존재 시 덮어쓰기
- `--driver-path`: 로컬 `chromedriver.exe` 경로 지정(오프라인 환경 대응)

## 저장 구조

```text
downloads/fss_audio/
  대출사기형/
  수사기관사칭형/
```

- 파일명은 각 게시물의 제목으로 저장됩니다.
- 동일 제목이 이미 있으면 `_2`, `_3` 형태로 자동 저장됩니다.

## 동작 방식 (MVP)

1. 목록 페이지 순회 (`pageIndex` 기반)
2. 상세 링크/`nttId` 추출
3. 상세 페이지에서 음원 URL 탐지
4. `requests`로 파일 저장

## 참고

- 사이트 구조 변경 시 셀렉터/정규식 보정이 필요할 수 있습니다.
- 응답이 `text/html`인 경우 다운로드가 차단된 것으로 판단해 스킵합니다.
- 사내망/오프라인 환경에서는 아래처럼 로컬 드라이버를 지정하세요.

```powershell
# 방법 1) 인자로 직접 전달
python scripts\fss_audio_crawler.py --boards loan --start 1 --end 1 --headless --driver-path "C:\tools\chromedriver.exe"

# 방법 2) 환경변수 사용
$env:CHROMEDRIVER="C:\tools\chromedriver.exe"
python scripts\fss_audio_crawler.py --boards loan --start 1 --end 1 --headless
```
