# Lezhin Discount Notifier

레진코믹스 특정 작품의 할인 여부를 확인하고, 새로운 할인이 생기면 지정한 대상으로 알림을 보내는 Python 자동화 스크립트입니다.

설정 편의성을 위해 자주 바꾸는 값은 [settings.json](/C:/_Main/Codex/웹툰할인알리미/settings.json)에서 관리하고, 비밀번호나 토큰만 환경변수 또는 GitHub Secrets로 관리하도록 구성했습니다.

지원 알림 대상:

- 이메일
- 카카오톡 `나에게 보내기`
- 카카오톡 친구 발송

## 구성 파일

- `main.py`: 전체 실행 흐름, 상태 비교, JSON 저장
- `config.py`: `settings.json` + 환경변수 병합 로드
- `checker.py`: 레진 페이지 조회 및 할인 파싱
- `notifier.py`: 알림 인터페이스
- `email_notifier.py`: SMTP 이메일 발송
- `kakao_notifier.py`: 카카오 액세스 토큰 갱신 및 카카오톡 발송
- `settings.json`: 웹툰 목록, 알림 대상, 실행 옵션
- `state.json`: 이전 실행 상태와 카카오 리프레시 토큰 상태 저장
- `.github/workflows/check.yml`: GitHub Actions 자동 실행

## 요구 환경

- Python 3.10+
- `requests`
- `beautifulsoup4`
- Gmail 앱 비밀번호 또는 Kakao Developers 앱

## 설치 방법

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4
```

Windows PowerShell에서는:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install requests beautifulsoup4
```

## 설정 방법

기본 사용 흐름은 두 단계입니다.

1. [settings.json](/C:/_Main/Codex/웹툰할인알리미/settings.json)에서 웹툰 목록과 알림 대상을 수정합니다.
2. 비밀번호나 토큰만 환경변수 또는 GitHub Secrets에 넣습니다.

### 1. `settings.json` 편집

`settings.json`에서 가장 자주 바꾸는 항목은 아래 세 군데입니다.

- `webtoons`: 할인 확인할 웹툰 목록
- `notification.provider`: 알림 방식
- `notification.email.recipients` 또는 `notification.kakao_friends`

현재 예시:

```json
{
  "webtoons": [
    { "title": "베드 파트너" },
    { "url": "https://www.lezhin.com/ko/comic/bed_partner" }
  ],
  "notification": {
    "provider": "email",
    "email": {
      "sender": "your-account@gmail.com",
      "recipients": ["your-email@example.com"]
    },
    "kakao_friends": {
      "names": ["홍길동"],
      "uuids": []
    }
  }
}
```

`notification.provider`는 아래 중 하나입니다.

- `email`
- `kakao_me`
- `kakao_friends`

자주 쓰는 수정 예시:

이메일로 받기

```json
{
  "notification": {
    "provider": "email",
    "email": {
      "sender": "mygmail@gmail.com",
      "recipients": ["me@example.com", "friend@example.com"]
    }
  }
}
```

내 카카오톡으로 받기

```json
{
  "notification": {
    "provider": "kakao_me"
  }
}
```

카카오 친구에게 보내기

```json
{
  "notification": {
    "provider": "kakao_friends",
    "kakao_friends": {
      "names": ["홍길동", "김철수"],
      "uuids": []
    }
  }
}
```

### 2. 민감정보는 환경변수로 설정

이메일 사용 시:

```powershell
$env:EMAIL_APP_PASSWORD="your-16-char-app-password"
```

카카오 사용 시:

```powershell
$env:KAKAO_REST_API_KEY="your-rest-api-key"
$env:KAKAO_CLIENT_SECRET="your-client-secret"
$env:KAKAO_REFRESH_TOKEN="your-refresh-token"
```

### 환경변수 우선순위

필요하면 기존처럼 환경변수만으로도 덮어쓸 수 있습니다.

- `LEZHIN_WEBTOONS`
- `NOTIFICATION_PROVIDER`
- `EMAIL_SENDER`
- `EMAIL_RECIPIENTS`
- `KAKAO_FRIEND_NAMES`
- `KAKAO_FRIEND_UUIDS`
- `SETTINGS_PATH`
- `STATE_PATH`
- `REQUEST_TIMEOUT_SECONDS`

## 이메일 설정 방법

Gmail을 사용할 경우:

1. Google 계정에서 2단계 인증을 켭니다.
2. 앱 비밀번호를 발급받습니다.
3. `settings.json`의 `notification.email.sender`에 Gmail 주소를 넣습니다.
4. `settings.json`의 `notification.email.recipients`에 받을 이메일 주소 목록을 넣습니다.
5. `EMAIL_APP_PASSWORD` 환경변수 또는 GitHub Secret에 앱 비밀번호를 넣습니다.

기본 SMTP 값은 Gmail 기준으로 아래처럼 동작합니다.

- `SMTP_HOST=smtp.gmail.com`
- `SMTP_PORT=587`

## 카카오 설정 방법

1. Kakao Developers에서 앱을 생성합니다.
2. 앱에서 `카카오 로그인`을 활성화합니다.
3. 동의항목에 `카카오톡 메시지 전송(talk_message)`를 추가합니다.
4. `제품 링크 관리`에서 웹 도메인에 `https://www.lezhin.com`을 등록합니다.
5. OAuth 인증 코드 플로우로 `refresh_token`을 발급받습니다.

인가 코드 요청 예시:

```text
https://kauth.kakao.com/oauth/authorize?response_type=code&client_id=REST_API_KEY&redirect_uri=REDIRECT_URI&scope=talk_message
```

인가 코드로 토큰 교환 시 `refresh_token`이 내려오며, 이 값을 `KAKAO_REFRESH_TOKEN`에 넣으면 됩니다. `KAKAO_CLIENT_SECRET`은 기본적으로 필요한 경우가 많아서 함께 설정하는 것을 권장합니다.

친구에게 보내기를 쓸 경우 추가로 확인할 점:

1. 카카오 친구 메시지 발송 권한이 앱에 허용되어 있어야 합니다.
2. 친구 UUID는 카카오 친구 목록 조회 API 또는 피커로 얻어야 합니다.
3. 닉네임으로 지정하려면 동의항목에 `카카오 서비스 내 친구목록`도 필요합니다.
4. 한 번에 최대 5명까지 전송되며, 그 이상은 스크립트가 자동으로 나눠서 보냅니다.

## 실행 방법

```bash
python main.py
```

테스트 알림만 바로 보내고 싶으면:

```bash
python main.py --test-notification
```

이 모드는 실제 레진 할인 조회를 하지 않고, 현재 설정된 알림 대상에게 샘플 할인 메시지를 1회 발송합니다.

- 이메일 설정이면 테스트 메일 발송
- `kakao_me`면 내 카카오톡으로 테스트 발송
- `kakao_friends`면 설정된 친구에게 테스트 발송

테스트 모드는 `state.json`의 웹툰 할인 상태는 바꾸지 않고, `last_test_notification_at`만 기록합니다.

동작 순서:

1. 설정된 작품 목록을 순회합니다.
2. 레진 페이지를 `requests` + `BeautifulSoup`으로 파싱합니다.
3. 할인 배너에서 할인가, 할인율, 기간을 추출합니다.
4. `state.json`과 비교해서 새 할인만 설정된 알림 대상으로 보냅니다.
5. 실행 결과를 `state.json`에 저장합니다.

## 할인 파싱 방식

현재 스크립트는 작품 상세 페이지에 노출되는 할인 배너 텍스트를 우선 파싱합니다.

지원 예시:

- `[2 → 1코인] 파격할인 이벤트! (4/9 목요일 정오까지)`
- `이벤트! 모든 회차 1코인 (3/26 목요일 정오까지)`
- `전 회차 1코인 할인`

참고:

- 레진 페이지에 원가가 함께 노출되지 않는 경우 `discount_rate`와 `original_price`는 `null`로 저장될 수 있습니다.
- 제목 기반 검색은 레진 검색 결과에서 첫 번째 작품 URL을 찾아 사용하므로, 동명이작이 있으면 URL 지정 방식이 더 안전합니다.

## state.json

`state.json`에는 작품별 이전 할인 상태뿐 아니라, 카카오 토큰 갱신 결과가 저장될 수 있습니다. 카카오 리프레시 토큰이 갱신되면 이 파일에 최신 값이 저장되므로 외부에 노출되지 않도록 주의하세요.

초기 예시:

```json
{
  "webtoons": {},
  "meta": {},
  "kakao": {}
}
```

## GitHub Actions 설정

워크플로 파일은 `.github/workflows/check.yml`에 포함되어 있습니다.

GitHub Actions의 cron은 UTC 기준입니다.

- `30 23 * * *` = 매일 `08:30 KST`

주요 GitHub Secrets:

- 이메일 사용 시: `EMAIL_APP_PASSWORD`
- 카카오 사용 시: `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_REFRESH_TOKEN`

웹툰 목록, 알림 방식, 이메일 수신자, 카카오 친구 이름은 기본적으로 저장소의 `settings.json`에서 관리하면 됩니다.

이 워크플로는 다음을 수행합니다.

1. 매일 오전 8시 30분(KST)에 실행
2. Python 설치
3. 의존성 설치
4. `state.json` 캐시 복원
5. 스크립트 실행
6. 최신 `state.json`을 캐시에 저장

`state.json`을 캐시하는 이유는 GitHub Actions 러너가 매 실행마다 새로 생성되기 때문입니다. 캐시가 없으면 이전 실행 결과와 갱신된 카카오 리프레시 토큰을 유지할 수 없습니다.

## 주의사항

- `settings.json`의 `notification.provider`가 `email`이면 이메일로, `kakao_me`면 본인 카카오톡으로, `kakao_friends`면 지정한 친구에게 보냅니다.
- 카카오 친구 발송은 카카오 앱 권한과 사용자 동의가 준비되지 않으면 동작하지 않을 수 있습니다.
- 카카오 메시지 템플릿 링크는 Kakao Developers의 `제품 링크 관리`에 등록된 도메인만 사용할 수 있습니다.
- 레진 페이지 구조가 바뀌면 `checker.py`의 파싱 로직을 조정해야 할 수 있습니다.
- 일부 작품은 로그인 상태 또는 국가/연령 설정에 따라 응답 내용이 달라질 수 있습니다.
