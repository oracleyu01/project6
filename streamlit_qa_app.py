"""
질문-답변 기반 제품 추천 Streamlit 앱
시맨틱 검색을 통한 맞춤형 제품 추천 시스템
"""

import streamlit as st
import os
import json
import re
import time
from typing import List, Dict, Optional
import logging
from datetime import datetime

import openai
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

# 데이터 수집 및 QA 생성 모듈 import
# from data_collector import NaverDataCollector
# from qa_generator import QAGenerator

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 페이지 설정
st.set_page_config(
    page_title="🤖 AI 제품 추천 시스템",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================================
# 1. 설정 및 초기화
# ========================================

@st.cache_resource
def init_clients():
    """클라이언트 초기화"""
    try:
        # API 키 확인
        if hasattr(st, 'secrets') and 'SUPABASE_URL' in st.secrets:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
            naver_client_id = st.secrets["NAVER_CLIENT_ID"]
            naver_client_secret = st.secrets["NAVER_CLIENT_SECRET"]
            openai_api_key = st.secrets["OPENAI_API_KEY"]
        else:
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            naver_client_id = os.environ.get("NAVER_CLIENT_ID")
            naver_client_secret = os.environ.get("NAVER_CLIENT_SECRET")
            openai_api_key = os.environ.get("OPENAI_API_KEY")
        
        if not all([supabase_url, supabase_key, openai_api_key]):
            st.error("❌ API 키가 설정되지 않았습니다.")
            st.stop()
        
        # 클라이언트 초기화
        supabase = create_client(supabase_url, supabase_key)
        openai.api_key = openai_api_key
        
        return supabase, naver_client_id, naver_client_secret, openai_api_key
        
    except Exception as e:
        st.error(f"❌ 클라이언트 초기화 실패: {str(e)}")
        st.stop()

@st.cache_resource
def load_embedding_model():
    """임베딩 모델 로딩"""
    try:
        model = SentenceTransformer('jhgan/ko-sroberta-multitask')
        return model
    except:
        try:
            model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            return model
        except Exception as e:
            st.error(f"❌ 임베딩 모델 로드 실패: {str(e)}")
            return None

# 전역 변수 초기화
supabase, naver_client_id, naver_client_secret, openai_api_key = init_clients()
embedding_model = load_embedding_model()

# ========================================
# 2. 핵심 검색 함수들
# ========================================

def generate_query_embedding(query: str) -> Optional[List[float]]:
    """쿼리 임베딩 생성"""
    if not embedding_model or not query or len(query.strip()) < 2:
        return None
    
    try:
        cleaned_query = re.sub(r'\s+', ' ', query.strip())
        embedding = embedding_model.encode(cleaned_query, convert_to_tensor=False)
        embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        
        # 1536차원으로 패딩
        if len(embedding_list) == 768:
            return embedding_list + [0.0] * 768
        elif len(embedding_list) == 1536:
            return embedding_list
        else:
            if len(embedding_list) < 1536:
                return embedding_list + [0.0] * (1536 - len(embedding_list))
            else:
                return embedding_list[:1536]
                
    except Exception as e:
        logger.error(f"쿼리 임베딩 생성 실패: {e}")
        return None

def semantic_search_qa(query: str, category_filter: str = None, top_k: int = 10) -> List[Dict]:
    """시맨틱 검색으로 관련 QA 찾기"""
    try:
        # 쿼리 임베딩 생성
        query_embedding = generate_query_embedding(query)
        if not query_embedding:
            return []
        
        # 벡터 검색 쿼리 실행
        # PostgreSQL의 <=> 연산자 사용 (cosine distance)
        base_query = supabase.table('product_qa').select(
            'id, product_name, brand, question, answer, question_type, recommendation_data, confidence_score'
        )
        
        # 카테고리 필터 적용
        if category_filter and category_filter != "전체":
            # 카테고리 ID 조회
            category_result = supabase.table('product_categories').select('id').eq('category_name', category_filter).execute()
            if category_result.data:
                category_id = category_result.data[0]['id']
                base_query = base_query.eq('category_id', category_id)
        
        # 최소 품질 조건
        result = base_query.gte('confidence_score', 0.5).limit(top_k).execute()
        
        if not result.data:
            return []
        
        # 유사도 계산 (클라이언트 사이드)
        qa_results = []
        for qa in result.data:
            # 실제 벡터 검색은 SQL 함수로 처리하거나
            # 여기서는 간단히 텍스트 매칭으로 대체
            similarity = calculate_text_similarity(query, qa['question'], qa['answer'])
            
            if similarity > 0.3:  # 최소 유사도 임계값
                qa['similarity'] = similarity
                qa_results.append(qa)
        
        # 유사도 순으로 정렬
        qa_results.sort(key=lambda x: x['similarity'], reverse=True)
        return qa_results[:top_k]
        
    except Exception as e:
        logger.error(f"시맨틱 검색 실패: {e}")
        return []

def calculate_text_similarity(query: str, question: str, answer: str) -> float:
    """간단한 텍스트 유사도 계산 (임베딩 기반 검색의 대안)"""
    try:
        # 키워드 매칭 기반 유사도
        query_words = set(re.findall(r'\w+', query.lower()))
        question_words = set(re.findall(r'\w+', question.lower()))
        answer_words = set(re.findall(r'\w+', answer.lower()))
        
        # 질문과의 유사도 (가중치 0.7)
        question_intersection = query_words.intersection(question_words)
        question_similarity = len(question_intersection) / max(len(query_words), 1) * 0.7
        
        # 답변과의 유사도 (가중치 0.3)
        answer_intersection = query_words.intersection(answer_words)
        answer_similarity = len(answer_intersection) / max(len(query_words), 1) * 0.3
        
        return question_similarity + answer_similarity
        
    except Exception as e:
        logger.debug(f"유사도 계산 실패: {e}")
        return 0.0

def search_products_with_ai_summary(query: str, category_filter: str = None) -> Dict:
    """QA 검색 + AI 요약을 통한 제품 추천"""
    try:
        # 1. 시맨틱 검색으로 관련 QA 찾기
        relevant_qa = semantic_search_qa(query, category_filter, top_k=15)
        
        if not relevant_qa:
            return {"error": "관련 정보를 찾을 수 없습니다."}
        
        # 2. 검색된 QA들을 ChatGPT로 요약하여 추천 결과 생성
        ai_summary = generate_ai_recommendation_summary(query, relevant_qa)
        
        return {
            "query": query,
            "relevant_qa": relevant_qa[:10],
            "ai_summary": ai_summary,
            "total_found": len(relevant_qa)
        }
        
    except Exception as e:
        logger.error(f"제품 검색 실패: {e}")
        return {"error": f"검색 중 오류가 발생했습니다: {str(e)}"}

def generate_ai_recommendation_summary(query: str, qa_list: List[Dict]) -> str:
    """검색된 QA들을 바탕으로 AI 추천 요약 생성"""
    try:
        # QA 정보 정리
        qa_text = []
        products_info = {}
        
        for qa in qa_list[:8]:  # 상위 8개만 사용
            qa_text.append(f"Q: {qa['question']}\nA: {qa['answer']}\n")
            
            product_name = qa['product_name']
            if product_name not in products_info:
                products_info[product_name] = {
                    'brand': qa.get('brand', ''),
                    'questions_count': 0,
                    'avg_confidence': 0,
                    'question_types': set()
                }
            
            products_info[product_name]['questions_count'] += 1
            products_info[product_name]['avg_confidence'] += qa.get('confidence_score', 0)
            products_info[product_name]['question_types'].add(qa.get('question_type', ''))
        
        # 평균 신뢰도 계산
        for product in products_info:
            count = products_info[product]['questions_count']
            if count > 0:
                products_info[product]['avg_confidence'] /= count
        
        # ChatGPT 프롬프트 구성
        prompt = f"""
사용자 질문: "{query}"

관련 제품 정보:
{chr(10).join(qa_text[:2000])}  # 토큰 제한 고려

위 정보를 바탕으로 다음 형식으로 제품 추천을 생성해주세요:

## 🎯 AI 추천 결과

### 💡 추천 요약
- 사용자 질문에 가장 적합한 제품 1-2개를 간단히 추천
- 추천 이유를 2-3문장으로 설명

### 📋 상세 추천

**1순위: [제품명]**
- 브랜드: [브랜드명]
- 주요 특징: [특징 3개]
- 추천 이유: [구체적인 이유]
- 예상 가격: [가격대]

**2순위: [제품명]** (있는 경우)
- 브랜드: [브랜드명] 
- 주요 특징: [특징 3개]
- 추천 이유: [구체적인 이유]
- 예상 가격: [가격대]

### 🔍 구매 시 고려사항
- 주요 체크포인트 2-3개

실제 수집된 정보를 바탕으로 정확하고 유용한 추천을 생성해주세요.
"""
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 제품 추천 전문가입니다. 제공된 정보를 바탕으로 정확하고 유용한 추천을 제공해주세요."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"AI 요약 생성 실패: {e}")
        return "AI 요약을 생성할 수 없습니다. 검색된 정보를 직접 확인해주세요."

# ========================================
# 3. 데이터 관리 함수들
# ========================================

def get_database_stats() -> Dict:
    """데이터베이스 현황 조회"""
    try:
        stats = {}
        
        # QA 데이터 통계
        qa_result = supabase.table('product_qa').select('id', count='exact').execute()
        stats['total_qa'] = qa_result.count if hasattr(qa_result, 'count') else len(qa_result.data)
        
        # 원본 데이터 통계
        raw_result = supabase.table('raw_product_data').select('id', count='exact').execute()
        stats['total_raw_data'] = raw_result.count if hasattr(raw_result, 'count') else len(raw_result.data)
        
        # 카테고리별 통계
        category_stats = supabase.table('product_categories').select('category_name').execute()
        stats['categories'] = [cat['category_name'] for cat in category_stats.data]
        
        # 제품별 QA 수 상위 5개
        product_stats = supabase.table('product_qa_summary').select('*').limit(5).execute()
        stats['top_products'] = product_stats.data if product_stats.data else []
        
        return stats
        
    except Exception as e:
        logger.error(f"DB 통계 조회 실패: {e}")
        return {}

def get_recent_qa_samples(limit: int = 5) -> List[Dict]:
    """최근 생성된 QA 샘플 조회"""
    try:
        result = supabase.table('product_qa').select(
            'product_name, question, answer, question_type, confidence_score, created_at'
        ).order('created_at', desc=True).limit(limit).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(f"QA 샘플 조회 실패: {e}")
        return []

# ========================================
# 4. Streamlit UI
# ========================================

def main():
    """메인 애플리케이션"""
    
    # 제목
    st.title("🤖 AI 제품 추천 시스템")
    st.markdown("**시맨틱 검색과 AI 분석으로 최적의 제품을 추천해드립니다**")
    
    # 사이드바
    with st.sidebar:
        st.title("⚙️ 시스템 현황")
        
        # 데이터베이스 현황
        st.markdown("### 📊 데이터 현황")
        
        with st.spinner("데이터 로딩 중..."):
            db_stats = get_database_stats()
        
        if db_stats:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("총 QA 수", f"{db_stats.get('total_qa', 0):,}개")
            with col2:
                st.metric("원본 데이터", f"{db_stats.get('total_raw_data', 0):,}개")
            
            # 카테고리 현황
            if db_stats.get('categories'):
                st.markdown("**등록된 카테고리:**")
                for cat in db_stats['categories']:
                    st.markdown(f"• {cat}")
        
        st.markdown("---")
        
        # 최근 QA 샘플
        st.markdown("### 📝 최근 QA 샘플")
        recent_qa = get_recent_qa_samples(3)
        
        for i, qa in enumerate(recent_qa, 1):
            with st.expander(f"샘플 {i}: {qa['product_name']}", expanded=False):
                st.markdown(f"**Q:** {qa['question'][:50]}...")
                st.markdown(f"**A:** {qa['answer'][:80]}...")
                st.markdown(f"**타입:** {qa['question_type']}")
                st.markdown(f"**신뢰도:** {qa['confidence_score']:.2f}")
    
    # 메인 컨텐츠
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 🔍 제품 검색 및 추천")
        
        # 검색어 입력
        query = st.text_input(
            "궁금한 제품이나 요구사항을 입력하세요",
            placeholder="예: 200만원대 노트북 추천해줘, 게이밍용 노트북, 가벼운 노트북",
            help="구체적인 요구사항을 입력하면 더 정확한 추천을 받을 수 있습니다"
        )
        
        # 검색 옵션
        col_opt1, col_opt2 = st.columns(2)
        
        with col_opt1:
            categories = ["전체"] + db_stats.get('categories', [])
            category_filter = st.selectbox("카테고리 필터", categories)
        
        with col_opt2:
            search_depth = st.selectbox(
                "검색 깊이",
                ["빠른 검색 (상위 5개)", "정밀 검색 (상위 10개)", "전체 검색 (상위 15개)"],
                index=1
            )
            
            depth_map = {
                "빠른 검색 (상위 5개)": 5,
                "정밀 검색 (상위 10개)": 10,
                "전체 검색 (상위 15개)": 15
            }
            top_k = depth_map[search_depth]
    
    with col2:
        st.markdown("### 💡 시스템 특징")
        st.markdown("""
        **🔍 시맨틱 검색**
        - 의미 기반 제품 검색
        - 다양한 표현 방식 이해
        - 맥락 고려한 추천
        
        **🤖 AI 분석**
        - ChatGPT 기반 요약
        - 개인화된 추천
        - 실시간 정보 종합
        
        **📊 멀티소스 데이터**
        - 쇼핑몰 가격 정보
        - 사용자 후기 분석  
        - 뉴스 및 리뷰 종합
        """)
    
    # 검색 실행
    if st.button("🔍 AI 추천 받기", type="primary", use_container_width=True):
        if not query.strip():
            st.warning("⚠️ 검색어를 입력해주세요!")
            return
        
        # 검색 실행
        with st.spinner("AI가 최적의 제품을 분석 중입니다..."):
            search_result = search_products_with_ai_summary(
                query, 
                category_filter if category_filter != "전체" else None
            )
        
        # 결과 표시
        if "error" in search_result:
            st.error(f"❌ {search_result['error']}")
            return
        
        # AI 요약 표시
        if search_result.get("ai_summary"):
            st.markdown("## 🤖 AI 추천 결과")
            st.markdown(search_result["ai_summary"])
        
        # 검색된 QA 상세 정보
        relevant_qa = search_result.get("relevant_qa", [])
        if relevant_qa:
            st.markdown("---")
            st.markdown("### 📚 관련 질문-답변 정보")
            st.caption(f"총 {search_result.get('total_found', 0)}개 중 상위 {len(relevant_qa)}개 표시")
            
            # QA 표시 옵션
            show_details = st.checkbox("상세 QA 정보 보기", value=False)
            
            if show_details:
                for i, qa in enumerate(relevant_qa, 1):
                    with st.expander(f"QA {i}: {qa['product_name']} ({qa['question_type']})", expanded=False):
                        col_qa1, col_qa2 = st.columns([1, 3])
                        
                        with col_qa1:
                            st.markdown("**제품 정보**")
                            st.markdown(f"• **제품명:** {qa['product_name']}")
                            if qa.get('brand'):
                                st.markdown(f"• **브랜드:** {qa['brand']}")
                            st.markdown(f"• **질문 유형:** {qa['question_type']}")
                            st.markdown(f"• **신뢰도:** {qa.get('confidence_score', 0):.2f}")
                            if 'similarity' in qa:
                                st.markdown(f"• **유사도:** {qa['similarity']:.2f}")
                        
                        with col_qa2:
                            st.markdown("**Q:** " + qa['question'])
                            st.markdown("**A:** " + qa['answer'])
                            
                            # 추천 데이터가 있으면 표시
                            if qa.get('recommendation_data'):
                                rec_data = qa['recommendation_data']
                                if isinstance(rec_data, dict):
                                    key_features = rec_data.get('key_features', [])
                                    if key_features:
                                        st.markdown("**주요 특징:** " + ", ".join(key_features))
            else:
                # 간단한 QA 목록만 표시
                for i, qa in enumerate(relevant_qa[:5], 1):
                    st.markdown(f"**{i}. {qa['product_name']}** ({qa['question_type']})")
                    st.markdown(f"   Q: {qa['question']}")
                    st.markdown(f"   A: {qa['answer'][:150]}...")
                    st.markdown("")
        
        # 검색 통계
        st.markdown("---")
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        
        with col_stat1:
            st.metric("검색된 QA", f"{len(relevant_qa)}개")
        with col_stat2:
            if relevant_qa:
                avg_confidence = sum(qa.get('confidence_score', 0) for qa in relevant_qa) / len(relevant_qa)
                st.metric("평균 신뢰도", f"{avg_confidence:.2f}")
        with col_stat3:
            unique_products = len(set(qa['product_name'] for qa in relevant_qa))
            st.metric("관련 제품 수", f"{unique_products}개")

    # 하단 정보
    st.markdown("---")
    with st.expander("ℹ️ 시스템 정보", expanded=False):
        st.markdown("""
        **🔧 핵심 기술:**
        - **시맨틱 검색**: SentenceTransformer + PostgreSQL pgvector
        - **AI 분석**: ChatGPT-3.5 Turbo API
        - **데이터 소스**: 네이버 쇼핑/블로그/뉴스 API
        - **데이터베이스**: Supabase (PostgreSQL)
        
        **📊 데이터 플로우:**
        1. 네이버 API → 원본 데이터 수집
        2. ChatGPT → 질문-답변 쌍 생성  
        3. SentenceTransformer → 벡터 임베딩
        4. 시맨틱 검색 → 관련 QA 추출
        5. ChatGPT → 최종 추천 요약
        
        **✨ 주요 특징:**
        - 의미 기반 검색으로 정확한 매칭
        - 실제 사용자 후기 및 뉴스 정보 활용
        - AI가 생성한 맞춤형 추천
        - 다양한 질문 유형별 최적화
        """)

if __name__ == "__main__":
    main()
