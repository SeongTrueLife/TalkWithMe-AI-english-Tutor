import streamlit as st
import utils
import os
import time
from streamlit_mic_recorder import mic_recorder 
import imageio_ffmpeg
import subprocess

# FFmpeg 경로 설정 (필수!)
if "ffmpeg_exe" not in st.session_state:
    st.session_state.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

# --- [1] 초기 설정 및 세션 초기화 ---
st.set_page_config(page_title="TalkWithMe", page_icon="🗣️", layout="wide")

# [CSS Styling] 모던하고 깔끔한 UI를 위한 커스텀 스타일 (Black & White Modern Dark Theme)
st.markdown("""
<style>
    /* 전체 배경 및 폰트 (다크 모드) */
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    
    /* 사이드바 스타일 */
    [data-testid="stSidebar"] {
        background-color: #262730;
        border-right: 1px solid #4b4b4b;
    }
    
    /* 제목 스타일 */
    h1 {
        color: #ffffff !important;
        font-weight: 700 !important;
        margin-bottom: 1rem !important;
    }
    h2, h3 {
        color: #e0e0e0 !important;
    }
    
    /* 채팅 메시지 스타일 (대비 강조) */
    .stChatMessage {
        background-color: transparent;
    }
    .stChatMessage[data-testid="stChatMessage"]:nth-child(odd) {
        /* User Message (White Bubble) */
        background-color: #ffffff;
        color: #000000;
        border-radius: 15px;
        padding: 15px;
        margin: 10px 0;
        box-shadow: 0 2px 5px rgba(255,255,255,0.1);
    }
    /* User Message 내부 텍스트 색상 강제 지정 */
    .stChatMessage[data-testid="stChatMessage"]:nth-child(odd) * {
        color: #000000 !important;
    }

    .stChatMessage[data-testid="stChatMessage"]:nth-child(even) {
        /* Assistant Message (Dark Grey Bubble) */
        background-color: #2b2d3e;
        color: #ffffff;
        border-radius: 15px;
        padding: 15px;
        margin: 10px 0;
        border: 1px solid #4b4b4b;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }
    /* Assistant Message 내부 텍스트 색상 강제 지정 */
    .stChatMessage[data-testid="stChatMessage"]:nth-child(even) * {
        color: #ffffff !important;
    }
    
    /* 버튼 스타일 (포인트 컬러: Cyan) */
    .stButton>button {
        background-color: transparent;
        color: #00e5ff;
        border: 1px solid #00e5ff;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #00e5ff;
        color: #000000;
        border-color: #00e5ff;
        box-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
    }
    
    /* 입력창 및 선택 박스 스타일 */
    .stSelectbox > div > div {
        background-color: #262730;
        color: white;
    }
    
    /* 메트릭(점수) 카드 스타일 */
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        color: #00e5ff !important;
    }
    
    /* Expander(상세보기) 스타일 */
    .streamlit-expanderHeader {
        background-color: #262730;
        color: white !important;
        border-radius: 8px;
        border: 1px solid #4b4b4b;
    }
    
    /* 구분선 스타일 */
    hr {
        border-color: #4b4b4b;
    }
</style>
""", unsafe_allow_html=True)

# 대화 기록을 저장할 저장소 (Context)
if "messages" not in st.session_state:
    st.session_state.messages = [] # 초기화는 사이드바 설정 후 진행

# 점수 기록을 저장할 저장소 (Score Card)
if "score_history" not in st.session_state:
    st.session_state.score_history = []

# 상태 관리 (대화 중 vs 리포트 보기)
if "mode" not in st.session_state:
    st.session_state.mode = "chat" # chat 또는 report

# [NEW] 마이크 리셋을 위한 키 관리
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0

# [Step 4] 피드백 리포트 저장소 (중복 호출 방지)
if "feedback_report" not in st.session_state:
    st.session_state.feedback_report = None

# --- [2] 사이드바 (설정 및 모드 전환) ---
with st.sidebar:
    st.header("⚙️ Control Panel")
    
    # [Step 2] 토픽 선택 기능 추가
    st.subheader("🎯 Topic Selection")
    topic = st.selectbox(
        "대화 주제를 선택하세요:",
        ("Free Talking (일상)", "Business Meeting (비즈니스)", "Job Interview (면접)", "Travel (여행)", "Restaurant (식당 주문)")
    )
    
    # 토픽에 따른 시스템 프롬프트 정의
    system_prompts = {
        "Free Talking (일상)": "You are a friendly English tutor. Engage in a casual daily conversation. Keep your response short and simple (maximum 2 sentences). Do not preach or give long explanations. Just respond naturally.",
        "Business Meeting (비즈니스)": "You are a professional business partner. Use formal English. Keep your response short and concise (maximum 2 sentences). Focus on the key point.",
        "Job Interview (면접)": "You are a strict interviewer. Ask challenging questions. Keep your response short (maximum 2 sentences). Wait for the user's answer.",
        "Travel (여행)": "You are a helpful local guide or airport staff. Keep your response short and simple (maximum 2 sentences). Give clear directions or answers.",
        "Restaurant (식당 주문)": "You are a waiter. Take the order politely. Keep your response short (maximum 2 sentences). Ask one question at a time."
    }
    
    # [중요] 토픽이 변경되면 대화 기록 초기화 (새로운 페르소나 적용)
    # 현재 세션에 저장된 토픽과 지금 선택된 토픽이 다르면 리셋
    if "current_topic" not in st.session_state:
        st.session_state.current_topic = topic
    
    if st.session_state.current_topic != topic:
        st.session_state.current_topic = topic
        st.session_state.messages = [{"role": "system", "content": system_prompts[topic]}]
        st.session_state.score_history = []
        st.session_state.mode = "chat"
        st.session_state.audio_key = 0
        st.session_state.feedback_report = None # 리포트 초기화
        st.rerun()

    # 앱이 처음 실행되어 messages가 비어있을 때 초기 프롬프트 설정
    if not st.session_state.messages:
         st.session_state.messages = [{"role": "system", "content": system_prompts[topic]}]

    st.divider()

    if st.button("🔄 대화 초기화 (Reset)"):
        st.session_state.messages = [{"role": "system", "content": system_prompts[topic]}] # 현재 선택된 토픽의 프롬프트로 리셋
        st.session_state.score_history = []
        st.session_state.mode = "chat"
        st.session_state.audio_key = 0 # 마이크 키도 초기화
        st.session_state.feedback_report = None # 리포트 초기화
        st.rerun()

    if st.session_state.mode == "chat":
        if st.button("📊 대화 종료 및 성적표 보기"):
            st.session_state.mode = "report"
            st.rerun()
    else:
        if st.button("🔙 대화 다시 시작하기"):
            st.session_state.mode = "chat"
            st.session_state.audio_key += 1 # 모드 변경 시 마이크 리셋
            st.session_state.feedback_report = None # 리포트 초기화
            st.rerun()

# --- [3] 메인 기능 구현 ---

# [Mode 1] 대화 모드
if st.session_state.mode == "chat":
    st.title(f"🗣️ {topic}") # 선택된 토픽을 제목으로 표시
    st.markdown(f"**{topic.split('(')[0]}** 모드입니다. AI와 상황에 맞춰 대화해보세요.")
    
    # 3-1. 이전 대화 내용 화면에 표시 (채팅창 느낌)
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

    # 3-2. 오디오 입력 (화면 하단)
    st.markdown("---")
    st.write("🎙️ **마이크 버튼을 눌러 말하고, 다시 눌러 멈추세요.**")
    
    # 마이크 레코더 (key를 동적으로 변경하여 강제 리셋 효과)
    audio = mic_recorder(
        start_prompt="🎤 Speak",
        stop_prompt="⏹️ Stop",
        key=f'chat_recorder_{st.session_state.audio_key}',
        just_once=True, # 한 번 녹음하면 리셋
        use_container_width=False
    )

    # 녹음이 완료되면 실행되는 로직
    if audio:
        # A. 파일 변환 (WebM -> WAV)
        audio_bytes = audio['bytes']
        with open("temp_input.webm", "wb") as f:
            f.write(audio_bytes)
            
        try:
            subprocess.run(
                [st.session_state.ffmpeg_exe, "-i", "temp_input.webm", "-ac", "1", "-ar", "16000", "input.wav", "-y"], 
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            
            # B. STT 및 발음 평가
            with st.spinner("👂 듣고 평가하는 중..."):
                stt_result = utils.speech_to_text("input.wav")
            
            # C. 결과 처리
            user_text = stt_result["text"]
            
            if user_text.startswith("Error") or user_text.startswith("System Error"):
                st.error("오디오 인식 실패. 다시 말해주세요.")
            else:
                # 1) 내 말 화면에 표시
                with st.chat_message("user"):
                    st.write(user_text)
                
                # 2) 대화 기록에 내 말 추가
                st.session_state.messages.append({"role": "user", "content": user_text})
                
                # 3) 점수 기록장에 몰래 저장
                scores = {
                    "text": user_text,
                    "accuracy": stt_result.get("accuracy_score", 0),
                    "fluency": stt_result.get("fluency_score", 0),
                    "pronunciation": stt_result.get("pronunciation_score", 0)
                }
                st.session_state.score_history.append(scores)

                # D. AI 답변 생성 (GPT)
                with st.spinner("🤖 생각 중..."):
                    ai_response = utils.get_openai_response(st.session_state.messages)
                
                # 1) AI 말 화면에 표시
                with st.chat_message("assistant"):
                    st.write(ai_response)
                
                # 2) 대화 기록에 AI 말 추가
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                
                # E. AI 음성 재생 (TTS)
                tts_file = utils.text_to_speech(ai_response)
                if tts_file:
                    with open(tts_file, "rb") as f:
                        autoplay_audio = f.read()
                    
                    # 자동 재생 (autoplay=True)
                    st.audio(autoplay_audio, format="audio/wav", autoplay=True)
                    
                    # 재생 후 임시 파일 삭제 (폴더에 파일 쌓임 방지)
                    os.remove(tts_file)
                
                # [핵심 수정] 다음 턴을 위해 마이크 키 업데이트
                st.session_state.audio_key += 1

        except Exception as e:
            st.error(f"오류 발생: {e}")

# [Mode 2] 성적표 모드 (Report)
elif st.session_state.mode == "report":
    st.title("📊 Conversation Report")
    
    if not st.session_state.score_history:
        st.info("대화 기록이 없습니다. 먼저 대화를 나눠보세요!")
    else:
        # 1. 전체 평균 점수 계산
        total_score = sum(item['pronunciation'] for item in st.session_state.score_history)
        avg_score = total_score / len(st.session_state.score_history)
        
        # [Step 4] GPT 기반 피드백 생성 (한 번만 호출)
        if st.session_state.feedback_report is None:
             with st.spinner("🤖 AI 선생님이 생활기록부를 작성 중입니다..."):
                st.session_state.feedback_report = utils.get_feedback_report(st.session_state.messages)
        
        # A. AI 선생님의 총평 (가장 상단에 배치)
        st.subheader("👩‍🏫 AI Tutor's Feedback")
        st.info(st.session_state.feedback_report)
        
        st.divider()

        # B. 정량적 분석 (점수)
        st.subheader("📈 Performance Metrics")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("총 발화 문장 수", f"{len(st.session_state.score_history)} 문장")
        with col2:
            st.metric("평균 발음 점수", f"{avg_score:.1f} / 100")
            
        st.divider()
        
        # C. 문장별 상세 분석
        st.subheader("📝 문장별 상세 피드백")
        
        for idx, item in enumerate(st.session_state.score_history):
            with st.expander(f"#{idx+1} : {item['text']} ({item['pronunciation']:.0f}점)"):
                c1, c2, c3 = st.columns(3)
                c1.metric("정확도", f"{item['accuracy']:.0f}")
                c2.metric("유창성", f"{item['fluency']:.0f}")
                c3.metric("종합점수", f"{item['pronunciation']:.0f}")
                
                score = item['pronunciation']
                if score >= 90:
                    st.success("🏆 원어민이세요? 완벽해요! (Excellent)")
                elif score >= 80:
                    st.success("🌟 아주 훌륭해요! (Great)")
                elif score >= 70:
                    st.info("👍 잘하고 있어요 조금만 더 해볼까요요! (Good)")
                elif score >= 60:
                    st.warning("💪 반복만이 살길이에요! (Not Bad)")
                else:
                    st.error("💡 발음 연습이 필요해요! (Needs Improvement)")

    # 성적표 모드에서도 돌아가기 버튼 추가 (메인 화면 하단)
    if st.button("🔙 대화 다시 시작하기 (New Session)"):
        st.session_state.mode = "chat"
        st.session_state.audio_key += 1
        st.session_state.feedback_report = None
        st.rerun()
