# family-guardian

영유아와 노부모를 노트북 웹캠으로 동시 모니터링하는 **AI 안전 데모 (Phase 1 MVP)**.

- **노인 모드 (elder)** — 자세 기반 낙상 감지, 의심 시 직전 10초 + 이후 영상만 보존
- **영유아 모드 (baby)** — 30분 단위 상시 녹화 + rPPG 호흡수 추정(참고용)

---

## ⚠️ 면책 조항

본 프로젝트는 **안전 모니터링 보조 도구**이며, **의료기기가 아닙니다**.

- 보호자의 직접 감독을 **대체할 수 없습니다**.
- 호흡 감지(rPPG)는 카메라 영상에서 추정한 **참고값**이며,
  조명·의복·움직임 등에 따라 큰 오차가 있습니다.
- 응급 상황에서는 즉시 119 등 전문 기관에 연락하십시오.

---

## 빠른 시작

```bash
# 1) 가상환경
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

# 2) 의존성
pip install -r requirements.txt

# 3) 환경설정
cp .env.example .env
$EDITOR .env

# 4) 테스트
pytest tests/ -v

# 5) 실행
python main.py
```

ESC 키로 즉시 종료, Ctrl+C 로 graceful 종료.

---

## 모드 전환

`.env` 의 `MODE` 값을 바꾸거나, 한 번만 사용할 때는 환경변수로 덮어쓰기:

```bash
MODE=elder python main.py    # 낙상 감지 + 사고 시에만 녹화 보존
MODE=baby  python main.py    # 상시 녹화 + 호흡 감지
```

---

## 텔레그램 봇 4단계

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 검색 → `/newbot` 으로 봇 생성
2. 안내에 따라 이름·username 지정 → **bot token** 발급받기
3. 만든 봇과 1:1 대화방을 열고 `/start` 메시지 전송
4. 브라우저에서 다음 URL 열기 (`YOUR_TOKEN` 부분 교체):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
   JSON 응답의 `"chat":{"id": ... }` 값을 복사

그리고 `.env` 에 입력:
```
NOTIFIER=telegram
TELEGRAM_BOT_TOKEN=12345:abcde...
TELEGRAM_CHAT_ID=987654321
```

---

## 🌐 웹 데모 (Railway 배포)

브라우저에서 카메라를 켜고 프레임을 서버에 업로드하면, 서버가 기존 파이프라인을
그대로 돌려 결과를 JSON 으로 돌려준다. Railway 같은 ephemeral 컨테이너용 구성이다.

### 로컬에서 먼저 띄워보기

```bash
. .venv/bin/activate
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

브라우저로 http://localhost:8000 접속 → "카메라 시작" 버튼.

### Railway 배포

1. Railway 콘솔에서 **New Project → Deploy from GitHub repo** 선택, 본 리포지토리 연결.
   리포 **루트**의 `Dockerfile` + `railway.json` 을 그대로 사용하므로 별도 설정 불필요.
2. **Variables** 탭에서 원하는 환경변수 설정:
   - `MODE` (기본 `elder`)
   - 텔레그램 사용 시 `NOTIFIER=telegram`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - S3 보관 시 `CLOUD_UPLOAD_ENABLED=true`, `S3_BUCKET`, AWS 자격증명
3. 빌드가 완료되면 자동 생성된 도메인(`*.up.railway.app`) 으로 접속.
   첫 startup 은 MediaPipe 모델 로딩으로 5~10초 걸린다.

### 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET    | `/`             | 데모 HTML (브라우저 카메라 → 프레임 업로드) |
| GET    | `/healthz`      | Railway healthcheck |
| GET    | `/state`        | 최신 분석 상태 (mode, state, torso_deg, bpm 등) |
| POST   | `/mode/{elder\|baby}` | 모드 전환 (recorder 재구성) |
| POST   | `/frame`        | JPEG 1장(`file=@frame.jpg`) → 분석 결과 JSON |

### 알려진 한계 (Railway 환경)

- **카메라 권한**: 브라우저 `getUserMedia` 는 HTTPS / localhost 에서만 동작.
  Railway 도메인은 자동 HTTPS 이므로 OK.
- **녹화 파일**: 컨테이너 디스크는 ephemeral. 영구 보관하려면 S3 업로드 활성화 필수.
- **단일 세션**: 데모는 단일 파이프라인 인스턴스로 다중 사용자 분리 없음.
  여러 사람이 동시에 접속하면 마지막 사람의 프레임 상태가 공유된다.

---

## 24시간 운영

### Linux / macOS — `run_forever.sh`

```bash
chmod +x run_forever.sh
./run_forever.sh
```

비정상 종료 시 5초 후 자동 재실행, `python main.py` 가 정상 종료(code 0)하면 루프 종료.

### Windows — `run_forever.ps1`

```powershell
# 최초 1회: 정책 허용
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

.\run_forever.ps1
```

### systemd (Linux 상시 등록)

`family-guardian.service` 의 `YOUR_USER` 자리표시자를 본인 계정명으로 치환 후 등록:

```bash
sed -i "s/YOUR_USER/$USER/g" family-guardian.service
sudo cp family-guardian.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now family-guardian
systemctl status family-guardian
```

로그는 `logs/guardian.log` (앱) + `logs/runner.log` (supervisor) 에 모인다.

---

## 디렉토리 구조

```
family-guardian/
├── config.py                  # 모든 임계값과 정책
├── main.py                    # 진입점
├── core/                      # 검출 / 녹화 모듈
│   ├── pose_detector.py       # MediaPipe Pose wrapper
│   ├── fall_detector.py       # 낙상 상태머신
│   ├── breathing_detector.py  # rPPG (참고용)
│   ├── ring_buffer.py         # 프리버퍼
│   ├── recorder.py            # baby 모드: 상시 분할 녹화
│   ├── incident_recorder.py   # elder 모드: 사고 영상만 보존
│   ├── event_state.py
│   └── logger.py
├── notifiers/                 # 알림 채널
│   ├── console.py
│   └── telegram.py
├── storage/
│   └── cloud_uploader.py      # 선택적 S3 업로드
└── tests/                     # pytest
```

---

## 알려진 한계 (Phase 1)

- MediaPipe 가 한 명만 추적 → 다인원 환경 부적합
- rPPG 는 카메라/조명에 매우 민감 → ±5~10 BPM 오차 정상
- 모바일 푸시 알림은 텔레그램만 지원
- 야간 IR 카메라 미지원 (가시광선 채널 의존)
