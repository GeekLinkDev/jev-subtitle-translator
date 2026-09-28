# GeekLink AI 자막 번역기 (Jev 품질 검사 포함)

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · **한국어**

LLM 기반 워크플로를 위한 오픈소스 SRT 번역 및 자막 품질 검사 도구입니다. SRT 파일을 번역하고, 모든 자막 큐를 그대로 유지하면서, Jev로 번역을 자동 검사할 수 있습니다.

**토픽:** SRT 번역 · 자막 QC · 자막 LLM · OpenRouter · Jev

![AI 자막 번역과 Jev가 사람의 검토가 필요한 줄을 표시하는 데모](docs/assets/translation-jev-qc.gif)

GPT, Claude, Gemini, DeepSeek, Grok 또는 기타 호환되는 OpenRouter 모델로 SRT 자막을 번역할 수 있습니다. 원본 자막의 순서와 타임스탬프는 그대로 유지되며, 누락된 번역과 의심스러운 의미 변화는 검토하기 쉽도록 명확하게 표시됩니다.

## 이 자막 번역기를 써야 하는 이유

- **원하는 LLM으로 SRT 자막 번역.** 언어 조합, 품질 요구 사항, 예산에 맞는 모델을 선택하세요.
- **모든 자막 큐 유지.** 원본 자막 번호, 순서, 타임스탬프가 바뀌지 않습니다.
- **소리 없이 사라지는 줄 방지.** 누락되거나 비어 있는 번역은 자막 ID 단위로 재시도되며, 끝내 해결되지 않으면 명확하게 표시됩니다.
- **Jev로 번역 자동 검토.** Jev는 완성된 모든 원문–번역 쌍을 검사하고, 사람이 검토할 만한 줄을 강조 표시합니다.
- **게시 전에 검토.** 원문, 번역, 검토 상태를 비교한 뒤 번역된 SRT와 QC 보고서를 다운로드하세요.
- **로컬 웹 인터페이스 또는 CLI.** 대화형으로 사용하거나 자동화된 자막 워크플로에 통합할 수 있습니다.

> **SRT 파일이 아니라 동영상에서 시작해야 하나요?**
>
> 이 오픈소스 프로젝트는 기존 SRT 자막의 번역과 검토에 초점을 맞추고 있습니다. [**GeekLink Subtitle Translator 사용해 보기 →**](https://geeklink.dev/subtitle-translator/)에서 동영상·오디오 전사, 자막 번역, 하드코딩 자막 추출, 결과 편집, 완성 동영상 내보내기까지 전체 워크플로를 이용할 수 있습니다.
>
> *Python 설정이나 모델 API 관리가 필요 없습니다.*

## 빠른 시작

**Python 3.10 이상**과 **OpenRouter API 키**가 필요합니다. macOS 또는 Linux에서:

```bash
git clone https://github.com/GeekLinkDev/jev-subtitle-translator.git
cd jev-subtitle-translator
bash run_web.sh
```

[http://127.0.0.1:8000](http://127.0.0.1:8000)을 연 다음:

1. **Translate + QC**(번역 + QC) 또는 **QC existing translation**(기존 번역 QC)을 선택합니다.
2. 원본 SRT를 업로드합니다. 단독 QC의 경우 번역된 SRT도 업로드합니다.
3. OpenRouter API 키를 입력하고 원본 언어와 대상 언어를 선택합니다.
4. **Translate + QC** 또는 **Run QC**를 클릭합니다. 단독 QC는 번역 모델을 호출하지 않습니다.
5. 강조 표시된 줄을 검토하고 JSON QC 보고서를 다운로드합니다. 번역 모드에서는 번역된 SRT도 제공됩니다.

동영상 파일은 선택 사항이며, 추가하면 로컬에서 자막을 미리 볼 수 있습니다.

## 자막 줄 누락을 막는 방법

```text
SRT를 파싱하고 모든 큐를 유지
        ↓
ID가 붙은 배치로 번역
        ↓
반환된 ID와 비어 있지 않은 번역 검증
        ↓
누락되었거나 비어 있는 ID만 재시도
        ↓
결정적 검사와 Jev 검토 실행
        ↓
원본 큐 목록으로 SRT 재구성
```

SRT는 로컬에서 파싱되며, 원본 자막 번호, 순서, 타임스탬프는 언어 모델 요청에 포함되지 않습니다. 각 텍스트 큐에는 안정적인 ID가 부여되고, JSON Schema 구조화 출력으로 번역됩니다.

응답을 받을 때마다 번역기는 예상된 ID이면서 중복되지 않고 비어 있지 않은 번역만 받아들입니다. 40개 자막 배치에서 유효한 결과가 35개만 돌아오면, 다음 요청에는 해결되지 않은 5개만 포함됩니다. 최종 SRT는 원본 큐 목록에서 재구성되므로, 번역 하나가 실패해도 뒤따르는 자막이 밀리거나 사라지지 않습니다.

그래도 번역할 수 없는 줄은 출력에서 빈 자막으로 자리를 유지하며, QC 보고서는 실패를 숨기는 대신 해당 줄을 수정 대상으로 표시합니다.

## Jev를 이용한 번역 품질 자동 검사

먼저 로컬 결정적 검사가 AI 모델 없이 빈 번역과 구조적 문제를 찾아냅니다. 그다음 Jev가 남은 모든 비어 있지 않은 원문–번역 쌍을 검토하고, **이 번역은 사람의 검토가 필요한가?**라는 한 가지 질문에 답합니다.

Jev는 다음과 같은 결함 가능성을 표시하도록 지시받습니다:

- 의미 누락, 근거 없는 추가, 부정의 반전.
- 이름, 숫자, 날짜, 단위의 변경 또는 누락.
- 잘리거나 반복되거나 명백히 잘못된 내용.

QC는 최대 40개 큐로 구성된 순서 있는 배치 단위로 실행됩니다. 한 큐를 판단하기 전에, 검토 모델은 문장이나 화자 턴에 따라 해당 배치 안의 앞뒤 큐를 필요한 만큼 살펴볼 수 있습니다. 의미가 큐 경계를 넘어 자연스럽게 이동한 경우는 표시되지 않으며, 여러 큐에 걸친 문장이 전체적으로 완전하다면 그 범위의 모든 큐가 통과해야 합니다. 토큰 중간에서 단어가 눈에 띄게 잘린 경우에는 주변 문맥으로 이해할 수 있더라도 검토가 필요한 결함으로 남습니다. 규칙은 정밀도(precision) 우선입니다. 불확실하거나 단순한 문체 차이는 통과시켜, 보고서가 정말로 사람의 주의가 필요한 줄에만 집중하도록 합니다.

Jev의 표시는 자막을 확인해 보라는 제안일 뿐, 틀렸다는 증거가 아닙니다. Jev는 번역을 다시 쓰지 않으며 오류를 놓칠 수도 있습니다. [검토 규칙](src/jev_subtitle_translator/qc.py)과 [OpenRouter 요청](src/jev_subtitle_translator/openrouter.py)은 소스 코드에서 확인할 수 있습니다.

## 지원하는 입력, 모델, 출력

- **자막 형식:** SRT 입력과 번역된 SRT 출력.
- **번역 모델:** 엄격한 JSON Schema 출력을 지원하는 OpenRouter 모델. 사용 가능한 GPT, Claude, Gemini, DeepSeek, Grok 모델을 포함합니다.
- **언어:** 선택한 번역 모델이 지원하는 모든 원본·대상 언어 조합.
- **품질 검사 모델:** 기본값은 OpenRouter의 `~typesafe/jev-latest` 별칭이며, 다른 OpenRouter 모델이나 로컬 모델로도 바꿀 수 있습니다. QC를 끄고 결정적 검사만 유지할 수도 있습니다.
- **로컬 모델:** Ollama, LM Studio, vLLM, llama.cpp 등 OpenAI 호환 서버.
- **보고서:** 번역된 SRT와 줄 단위 번역·검토 상태가 담긴 JSON 보고서.

## 명령줄

SRT를 번역하고 Jev 검토를 자동 실행:

```bash
export OPENROUTER_API_KEY="your-api-key"

.venv/bin/jev-subtitle-translator translate input.srt \
  --source-language en --target-language de \
  --model openai/gpt-4o-mini --output translated.srt
```

다시 번역하지 않고 기존 번역만 검토:

```bash
export OPENROUTER_API_KEY="your-api-key"

.venv/bin/jev-subtitle-translator qc \
  --source input.srt --translation translated.srt \
  --source-language en --target-language de --output qc-report.json
```

번역 명령은 `translated.srt`와 `translated.srt.qc.json`을 생성합니다. 추가 번역 지침은 `--prompt`, 요청 조정은 `--batch-size`와 `--workers`를 사용하고, 전체 옵션은 각 명령의 `--help`로 확인하세요.

## 로컬 모델과 OpenAI 호환 모델

번역과 QC는 각각 OpenAI 호환 `/v1/chat/completions` 엔드포인트를 제공하는 어떤 서버든 지정할 수 있습니다. 웹 인터페이스에서 **Local / OpenAI-compatible**을 선택하고 base URL을 입력하세요. 예: Ollama는 `http://localhost:11434/v1`, LM Studio는 `http://localhost:1234/v1`, vLLM은 `http://localhost:8000/v1`.

```bash
# 로컬에서 번역하고 OpenRouter의 Jev로 검토
export OPENROUTER_API_KEY="your-api-key"
.venv/bin/jev-subtitle-translator translate input.srt \
  --source-language en --target-language de \
  --model qwen2.5:14b --base-url http://localhost:11434/v1 --output translated.srt

# 완전 로컬: 로컬 모델로 번역과 검토, OpenRouter 키 불필요
.venv/bin/jev-subtitle-translator translate input.srt \
  --source-language en --target-language de \
  --model qwen2.5:14b --base-url http://localhost:11434/v1 \
  --qc-model qwen2.5:14b --qc-base-url http://localhost:11434/v1 --output translated.srt
```

`OPENROUTER_API_KEY`는 openrouter.ai의 엔드포인트를 사용할 때만 필요합니다. 로컬 서버가 키를 요구하면 `LOCAL_API_KEY`를 설정하세요. Jev 모델(`typesafe/jev-*` 및 `~typesafe/jev-*`)은 OpenRouter의 Decisions 엔드포인트를 사용하므로 OpenRouter가 필요합니다. 다른 QC 모델은 chat을 통해 동일한 검토 지침을 받고 줄마다 `needs_review` 판정을 반환합니다. 의미 QC를 건너뛰려면 `--qc-model none`을 사용하세요.

번역기는 JSON Schema 구조화 출력을 요청합니다. 현재 대부분의 로컬 서버가 이를 지원하며, 모델이 JSON을 텍스트나 markdown으로 감싸 반환하더라도 객체는 자동으로 추출됩니다. 소형 로컬 모델은 ID를 더 자주 빠뜨릴 수 있지만, 그런 줄도 다른 실패와 마찬가지로 재시도된 뒤 표시됩니다.

## 자주 묻는 질문

### SRT 타임스탬프가 유지되나요?

네. 자막 번호, 순서, 타임스탬프는 로컬에서 파싱되고 저장됩니다. 번역을 위해 전송되는 것은 대사 텍스트와 그 안정적인 ID뿐입니다.

### 자막 줄 누락은 어떻게 막나요?

모든 모델 응답은 예상된 자막 ID와 대조해 검증됩니다. 누락되거나 비어 있는 결과는 따로 재시도되며, 해결되지 않은 줄은 출력과 QC 보고서에 계속 표시됩니다.

### Jev가 잘못된 번역을 자동으로 고치나요?

아니요. Jev는 사람의 검토가 필요할 수 있는 자막을 찾아낼 뿐, 번역을 대체하거나 다시 쓰지 않습니다.

### 이 자막 번역기는 무료인가요?

이 프로젝트는 GPL 라이선스의 무료 오픈소스입니다. OpenRouter API 키는 직접 준비해야 하며, 번역과 Jev 요청에는 OpenRouter 요금이 발생할 수 있습니다. 인터페이스는 로컬에서 실행되지만, 자막 텍스트는 OpenRouter와 선택한 모델 제공업체로 전송됩니다.

### 이 프로젝트와 GeekLink의 차이점은 무엇인가요?

이 프로젝트는 기존 SRT 파일의 번역과 검토에 집중합니다. [GeekLink](https://geeklink.dev/subtitle-translator/)는 전사, 번역, 하드코딩 자막 추출, 자막 편집, 동영상 내보내기를 모두 갖춘 크리에이터용 데스크톱 앱입니다.

## 개발 및 라이선스

`.venv/bin/python -m pip install -e ".[dev]"`로 테스트 의존성을 설치하고 `.venv/bin/python -m pytest -q`를 실행하세요. 수정 사항이나 재현 가능한 자막 예시로 기여하려면 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

[GPL-3.0-or-later](LICENSE) 라이선스로 배포됩니다. Copyright (C) 2026 GeekLinkDev.
