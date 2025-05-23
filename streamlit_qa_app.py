"""
질문-답변 기반 제품 추천 Streamlit 앱 (개선 버전)
AI 요약 대신 검색된 QA의 answer를 직접 출력하여 더 빠르고 정확한 추천 제공
"""

import streamlit as st
import os
import json
import re
import time
from typing import List, Dict, Optional
import logging
from datetime import datetime

from supabase import create_client, Client

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
        else:
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
        
        if not all([supabase_url, supabase_key]):
            st.error("❌ Supabase API 키가 설정되지 않았습니다.")
            st.stop()
        
        # 클라이언트 초기화
        supabase = create_client(supabase_url, supabase_key)
        
        return supabase
        
    except Exception as e:
        st.error(f"❌ 클라이언트 초기화 실패: {str(e)}")
        st.stop()

# 전역 변수 초기화
supabase = init_clients()

# ========================================
# 2. 핵심 검색 함수들
# ========================================

def text_based_search_qa(query: str, category_filter: str = None, top_k: int = 10) -> List[Dict]:
    """텍스트 기반 검색으로 관련 QA 찾기 (빠르고 간단)"""
    try:
        # 디버깅 정보
        st.write(f"🔍 검색어: '{query}'")
        
        # 검색어에서 핵심 키워드 추출
        keywords = [word.strip() for word in query.split() if len(word.strip()) > 1]
        st.write(f"🔍 추출된 키워드: {keywords}")
        
        # 기본 쿼리
        base_query = supabase.table('product_qa').select('*')
        
        # 카테고리 필터 적용
        if category_filter and category_filter != "전체":
            category_result = supabase.table('product_categories').select('id').eq('category_name', category_filter).execute()
            if category_result.data:
                category_id = category_result.data[0]['id']
                base_query = base_query.eq('category_id', category_id)
        
        # 키워드별 검색 결과 수집
        all_results = []
        
        for keyword in keywords:
            if len(keyword) > 1:
                # 각 키워드에 대해 개별 검색
                try:
                    # 질문에서 검색
                    q_result = base_query.ilike('question', f'%{keyword}%').gte('confidence_score', 0.5).execute()
                    all_results.extend(q_result.data)
                    
                    # 답변에서 검색
                    a_result = base_query.ilike('answer', f'%{keyword}%').gte('confidence_score', 0.5).execute()
                    all_results.extend(a_result.data)
                    
                    # 제품명에서 검색
                    p_result = base_query.ilike('product_name', f'%{keyword}%').gte('confidence_score', 0.5).execute()
                    all_results.extend(p_result.data)
                    
                except Exception as e:
                    st.write(f"⚠️ 키워드 '{keyword}' 검색 중 오류: {e}")
                    continue
        
        # 중복 제거 (ID 기준)
        unique_results = {}
        for result in all_results:
            qa_id = result['id']
            if qa_id not in unique_results:
                unique_results[qa_id] = result
        
        final_results = list(unique_results.values())
        
        # 간단한 점수 계산 (키워드 매칭 수)
        for qa in final_results:
            score = 0
            qa_text = f"{qa['question']} {qa['answer']} {qa['product_name']}".lower()
            
            for keyword in keywords:
                if keyword.lower() in qa_text:
                    score += 1
            
            qa['relevance_score'] = score
        
        # 점수순으로 정렬
        final_results.sort(key=lambda x: (x['relevance_score'], x['confidence_score']), reverse=True)
        
        st.write(f"✅ 검색 완료: {len(final_results)}개 결과")
        
        return final_results[:top_k]
        
    except Exception as e:
        st.error(f"❌ 검색 실패: {e}")
        logger.error(f"텍스트 검색 실패: {e}")
        return []

def create_direct_recommendation(query: str, qa_list: List[Dict]) -> Dict:
    """검색된 QA 결과를 직접 정리하여 추천 생성"""
    try:
        if not qa_list:
            return {"error": "관련 정보를 찾을 수 없습니다."}
        
        # 제품별 정보 정리
        products_info = {}
        
        for qa in qa_list:
            product_name = qa['product_name']
            if product_name not in products_info:
                products_info[product_name] = {
                    'brand': qa.get('brand', ''),
                    'answers': [],
                    'question_types': set(),
                    'total_confidence': 0,
                    'count': 0,
                    'best_qa': qa  # 가장 관련성 높은 QA
                }
            
            products_info[product_name]['answers'].append({
                'question': qa['question'],
                'answer': qa['answer'],
                'type': qa['question_type'],
                'confidence': qa.get('confidence_score', 0),
                'relevance': qa.get('relevance_score', 0)
            })
            
            products_info[product_name]['question_types'].add(qa['question_type'])
            products_info[product_name]['total_confidence'] += qa.get('confidence_score', 0)
            products_info[product_name]['count'] += 1
            
            # 더 관련성 높은 QA로 업데이트
            if qa.get('relevance_score', 0) > products_info[product_name]['best_qa'].get('relevance_score', 0):
                products_info[product_name]['best_qa'] = qa
        
        # 평균 신뢰도 계산
        for product in products_info:
            info = products_info[product]
            info['avg_confidence'] = info['total_confidence'] / max(info['count'], 1)
            info['question_types'] = list(info['question_types'])
        
        # 제품을 관련성과 신뢰도로 정렬
        sorted_products = sorted(
            products_info.items(),
            key=lambda x: (
                x[1]['best_qa'].get('relevance_score', 0),
                x[1]['avg_confidence']
            ),
            reverse=True
        )
        
        return {
            "query": query,
            "products_info": dict(sorted_products),
            "total_found": len(qa_list),
            "total_products": len(products_info)
        }
        
    except Exception as e:
        logger.error(f"추천 생성 실패: {e}")
        return {"error": f"추천 생성 중 오류 발생: {str(e)}"}

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
    st.markdown("**빠른 검색과 정확한 답변으로 최적의 제품을 추천해드립니다**")
    
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
            placeholder="예: 도어락 추천해줘, 200만원대 노트북, 가벼운 노트북",
            help="구체적인 요구사항을 입력하면 더 정확한 추천을 받을 수 있습니다"
        )
        
        # 검색 옵션
        col_opt1, col_opt2 = st.columns(2)
        
        with col_opt1:
            categories = ["전체"] + db_stats.get('categories', [])
            category_filter = st.selectbox("카테고리 필터", categories)
        
        with col_opt2:
            search_depth = st.selectbox(
                "검색 개수",
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
        **⚡ 빠른 검색**
        - 텍스트 기반 즉시 검색
        - 키워드 매칭으로 정확한 결과
        - 실시간 답변 제공
        
        **🎯 정확한 답변**
        - 미리 준비된 전문 답변
        - 제품별 상세 정보
        - 다양한 질문 유형 지원
        
        **📊 풍부한 데이터**
        - 쇼핑몰 가격 정보
        - 사용자 후기 분석  
        - 전문가 추천
        """)
    
    # 검색 실행
    if st.button("🔍 제품 추천 받기", type="primary", use_container_width=True):
        if not query.strip():
            st.warning("⚠️ 검색어를 입력해주세요!")
            return
        
        # 검색 실행
        with st.spinner("관련 제품 정보를 검색 중입니다..."):
            qa_results = text_based_search_qa(
                query, 
                category_filter if category_filter != "전체" else None,
                top_k
            )
        
        if not qa_results:
            st.error("❌ 관련 정보를 찾을 수 없습니다. 다른 키워드로 시도해보세요.")
            return
        
        # 추천 결과 생성
        recommendation = create_direct_recommendation(query, qa_results)
        
        if "error" in recommendation:
            st.error(f"❌ {recommendation['error']}")
            return
        
        # 추천 결과 표시
        st.markdown("## 🎯 제품 추천 결과")
        
        products_info = recommendation.get('products_info', {})
        
        # 상위 제품들 표시
        for i, (product_name, info) in enumerate(products_info.items(), 1):
            if i > 3:  # 상위 3개만 표시
                break
                
            with st.container():
                # 제품 헤더
                col_header1, col_header2 = st.columns([3, 1])
                
                with col_header1:
                    st.markdown(f"### {i}. {product_name}")
                    if info['brand']:
                        st.markdown(f"**브랜드:** {info['brand']}")
                
                with col_header2:
                    st.metric("신뢰도", f"{info['avg_confidence']:.2f}")
                
                # 최고 관련도 답변 표시
                best_qa = info['best_qa']
                
                st.markdown("#### 💬 주요 추천 정보")
                st.markdown(f"**Q:** {best_qa['question']}")
                
                # 답변을 예쁘게 표시
                with st.container():
                    st.markdown("**A:**")
                    st.info(best_qa['answer'])
                
                # 추가 정보 표시
                if len(info['answers']) > 1:
                    with st.expander(f"📚 {product_name} 추가 정보 ({len(info['answers'])-1}개 더)", expanded=False):
                        for j, qa_info in enumerate(info['answers'][1:], 2):
                            st.markdown(f"**Q{j}:** {qa_info['question']}")
                            st.markdown(f"**A{j}:** {qa_info['answer']}")
                            st.markdown(f"*유형: {qa_info['type']}, 신뢰도: {qa_info['confidence']:.2f}*")
                            st.markdown("---")
                
                # 제품 특징 정보
                rec_data = best_qa.get('recommendation_data', {})
                if isinstance(rec_data, dict) and rec_data.get('key_features'):
                    st.markdown("**🔖 주요 특징:**")
                    features_text = " • ".join(rec_data['key_features'])
                    st.markdown(f"• {features_text}")
                
                st.markdown("---")
        
        # 검색 통계 및 추가 정보
        st.markdown("### 📊 검색 결과 통계")
        
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        
        with col_stat1:
            st.metric("검색된 QA", f"{recommendation['total_found']}개")
        with col_stat2:
            st.metric("관련 제품", f"{recommendation['total_products']}개")
        with col_stat3:
            avg_confidence = sum(qa.get('confidence_score', 0) for qa in qa_results) / max(len(qa_results), 1)
            st.metric("평균 신뢰도", f"{avg_confidence:.2f}")
        with col_stat4:
            avg_relevance = sum(qa.get('relevance_score', 0) for qa in qa_results) / max(len(qa_results), 1)
            st.metric("평균 관련성", f"{avg_relevance:.1f}")
        
        # 전체 검색 결과 옵션
        if st.checkbox("🔍 전체 검색 결과 보기", value=False):
            st.markdown("### 📋 전체 검색 결과")
            
            for i, qa in enumerate(qa_results, 1):
                with st.expander(f"결과 {i}: {qa['product_name']} - {qa['question_type']}", expanded=False):
                    st.markdown(f"**제품:** {qa['product_name']} ({qa.get('brand', 'N/A')})")
                    st.markdown(f"**Q:** {qa['question']}")
                    st.markdown(f"**A:** {qa['answer']}")
                    
                    col_detail1, col_detail2, col_detail3 = st.columns(3)
                    with col_detail1:
                        st.metric("신뢰도", f"{qa.get('confidence_score', 0):.2f}")
                    with col_detail2:
                        st.metric("관련성", f"{qa.get('relevance_score', 0)}")
                    with col_detail3:
                        st.markdown(f"**유형:** {qa['question_type']}")

    # 하단 정보
    st.markdown("---")
    with st.expander("ℹ️ 시스템 정보", expanded=False):
        st.markdown("""
        **🔧 핵심 기술:**
        - **텍스트 검색**: 키워드 기반 빠른 매칭
        - **데이터베이스**: Supabase (PostgreSQL)
        - **답변 시스템**: 미리 준비된 전문 답변 직접 제공
        
        **📊 데이터 플로우:**
        1. 사용자 검색어 입력
        2. 키워드 추출 및 텍스트 매칭
        3. 관련 QA 검색 및 정렬
        4. 제품별 정보 정리
        5. 직접 답변 제공
        
        **✨ 주요 장점:**
        - 즉시 검색 및 답변 제공
        - 전문가가 작성한 정확한 답변
        - 다양한 제품 카테고리 지원
        - 신뢰도 기반 결과 정렬
        """)

if __name__ == "__main__":
    main()
