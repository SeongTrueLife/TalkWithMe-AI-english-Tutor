import os
import uuid
import streamlit as st
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk
from openai import AzureOpenAI

#1. 환경 변수 로드(.env 파일 불러오기)
load_dotenv()

# [NEW] 환경 변수 가져오기 헬퍼 함수 (로컬/배포 환경 호환)
def get_secret(key):
    if key in st.secrets:
        return st.secrets[key]
    return os.getenv(key)

#1. OpenAI 설정(뇌)
def get_openai_response(messages):
    try:
        client = AzureOpenAI(
        api_key= get_secret("AZURE_OPENAI_API_KEY"),
        api_version=get_secret("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=get_secret("AZURE_OPENAI_ENDPOINT")
    )

        deployment_name = get_secret("AZURE_OPENAI_DEPLOYMENT_NAME")
        print(f"AI 모델{deployment_name}에게 질문하는 중...")

        response = client.chat.completions.create(
            model=deployment_name,
            messages= messages
        )
        answer = response.choices[0].message.content
        return answer
    except Exception as e:
        return f"에러발생: {e}"

# [NEW] 성적표 생성을 위한 GPT 함수 (총평 + 문법 교정)
def get_feedback_report(messages):
    """
    전체 대화 기록을 분석하여 종합 리포트(총평, 문법 교정)를 생성합니다.
    """
    try:
        client = AzureOpenAI(
            api_key=get_secret("AZURE_OPENAI_API_KEY"),
            api_version=get_secret("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=get_secret("AZURE_OPENAI_ENDPOINT")
        )

        deployment_name = get_secret("AZURE_OPENAI_DEPLOYMENT_NAME")
        
        # 시스템 프롬프트: 선생님 역할 부여
        system_prompt = """
        You are a helpful English tutor. Analyze the user's conversation history.
        Provide the output in the following format(Korean):
        
        1. **종합 평가 (Overall Feedback)**: 
           - Summarize the user's English skills, strengths, and areas for improvement in 2-3 sentences.
        
        2. **주요 문법 교정 (Grammar Corrections)**: 
           - Pick up to 3 sentences with grammatical errors from the user's input.
           - Format: 'User said: ...' -> 'Corrected: ...' (Explanation in Korean).
           - If there are no major errors, praise the user's grammar.
        """

        # 분석을 위한 메시지 구성 (시스템 프롬프트 + 대화 내역)
        # 대화 내역 중 User와 Assistant의 대화만 추려서 전달
        conversation_log = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages if msg['role'] != 'system'])
        
        prompt_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the conversation log:\n{conversation_log}"}
        ]

        response = client.chat.completions.create(
            model=deployment_name,
            messages=prompt_messages,
            temperature=0.7 # 약간의 창의성 허용
        )
        
        return response.choices[0].message.content

    except Exception as e:
        return f"피드백 생성 중 오류 발생: {e}"


#2. Azure STT + 발음 평가 (귀)
def speech_to_text(audio_file_path):
    try:
        speech_key = get_secret("SPEECH_KEY")
        speech_region = get_secret("SPEECH_REGION")

        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.speech_recognition_language = "en-US" #나중에 삭제할수도 있음-사용자가한국어쓸때

        #오디오 파일 설정.
        audio_config = speechsdk.audio.AudioConfig(filename=audio_file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        #[핵심] 발음 평가 설정 추가!
        #reference_text를 비워두면("") Azure가 들린 대로 평가해 (Unscripted Assessment)
        pronunciation_config = speechsdk.PronunciationAssessmentConfig(
            reference_text="",
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
            enable_miscue=True
        )

        #설정 적용
        pronunciation_config.apply_to(recognizer)

        #인식 시작
        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            #평가 결과(JSON)을 뜯어내 점수 확인
            pronunciation_result = speechsdk.PronunciationAssessmentResult(result)

            #결과 딕셔너리 생성
            output = {
                "text": result.text,
                "accuracy_score": pronunciation_result.accuracy_score,
                "fluency_score": pronunciation_result.fluency_score,
                "pronunciation_score": pronunciation_result.pronunciation_score
            }
            return output
        
        elif result.reason == speechsdk.ResultReason.NoMatch:
            return {
                "text": "죄송합니다. 아무것도 듣지 못했어요.", 
                "accuracy_score": 0, 
                "fluency_score": 0, 
                "pronunciation_score": 0
            }

        elif result.reason == speechsdk.ResultReason.Canceled:
            return {
                "text": f"오류: {result.cancellation_details.reason_details}", 
                "accuracy_score": 0, 
                "fluency_score": 0, 
                "pronunciation_score": 0
            }
    
    except Exception as e:
        return {
            "text": f"시스템 에러: {e}", 
            "accuracy_score": 0, 
            "fluency_score": 0, 
            "pronunciation_score": 0
        }


#Azure TTS(ai의 입)
def text_to_speech(text):
    try:
        speech_key = get_secret('SPEECH_KEY')
        speech_region = get_secret('SPEECH_REGION')
        
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.speech_synthesis_voice_name = 'en-US-JennyNeural'

        # 파일명 충돌 방지를 위해 UUID 사용
        file_name = f"output_{uuid.uuid4()}.wav"
        audio_config = speechsdk.audio.AudioOutputConfig(filename=file_name)

        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return file_name
        else:
            print(f"TTS 에러: {result.cancellation_details.reason_details}")
            return None

    except Exception as e:
        print(f"TTS 시스템 에러: {e}")
        return None
