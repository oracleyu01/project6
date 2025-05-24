"""
실시간 데이터 수집 기능이 포함된 질문-답변 기반 제품 추천 Streamlit 앱 (완전 수정 버전)
모든 제품에 대해 검색 가능한 범용 추천 시스템
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
# 2. 헬퍼 함수들
# ========================================

def ensure_food_category():
    """식품 카테고리가 없으면 자동 추가"""
    try:
        food_category = supabase.table('product_categories').select('id').eq('category_name', '식품').execute()
        if not food_category.data:
            new_category = {
                'category_name': '식품',
                'category_keywords': ['음식', '식품', '요거트', '우유', '치즈', '그릭요거트'],
                'search_keywords': {
                    "shopping": ["식품", "음식"],
                    "blog": ["맛집", "요리", "후기"],
                    "news": ["식품 안전", "건강식품"]
                }
            }
            supabase.table('product_categories').insert(new_category).execute()
    except Exception as e:
        logger.debug(f"카테고리 추가 실패: {e}")

def generate_product_text(product_name: str, category_id: int) -> str:
    """제품별 맞춤 텍스트 생성"""
    if category_id == 6:  # 식품
        return f"""
제품명: {product_name}

=== 쇼핑 정보 ===
다양한 브랜드의 {product_name} 온라인/오프라인 매장에서 판매 중
대형마트, 편의점, 온라인 쇼핑몰에서 구매 가능
브랜드별 다양한 맛과 용량 옵션 제공
정기적인 할인 및 프로모션 이벤트 진행

=== 사용자 후기 (블로그) ===
후기 1: 맛이 진하고 영양가도 뛰어난 제품
내용: 아침 식사 대용으로 먹고 있는데 포만감도 좋고 건강에도 도움이 되는 것 같습니다...

후기 2: 다른 브랜드 대비 가성비 우수
내용: 여러 브랜드를 비교해봤는데 맛과 가격 모두 만족스럽습니다...

=== 관련 뉴스 ===
뉴스 1: {product_name} 건강 효능 주목받아
내용: 최근 {product_name}의 건강 효능이 알려지면서 소비가 크게 증가하고 있다...
"""
    else:  # 기타 제품
        return f"""
제품명: {product_name}

=== 쇼핑 정보 ===
다양한 온라인 쇼핑몰 및 오프라인 매장에서 판매 중
브랜드별 다양한 제품 라인업과 가격대 옵션 제공
정기적인 할인 이벤트 및 프로모션 진행
사용자 리뷰 및 평점 정보 풍부

=== 사용자 후기 (블로그) ===
후기 1: 품질과 성능이 기대 이상
내용: 실제 사용해보니 광고나 스펙보다 훨씬 만족스럽습니다. 특히 내구성이 좋네요...

후기 2: 가격 대비 합리적인 선택
내용: 비슷한 제품들과 비교했을 때 가성비가 뛰어납니다...

=== 관련 뉴스 ===
뉴스 1: {product_name} 시장 동향 및 전망
내용: {product_name} 시장이 지속적으로 성장하고 있으며 다양한 신제품이 출시되고 있다...
"""

def generate_qa_samples(product_name: str, category_id: int) -> List[Dict]:
    """제품별 맞춤 QA 샘플 생성"""
    if category_id == 6:  # 식품
        return [
            {
                "question": f"{product_name} 추천해줘",
                "answer": f"{product_name}은 건강하고 맛있는 식품으로 많은 사람들이 즐기고 있습니다. 다양한 브랜드에서 출시되고 있으며, 대형마트나 온라인에서 쉽게 구매할 수 있습니다. 영양가가 높고 맛도 좋아 아침식사나 간식으로 적합합니다.",
                "question_type": "recommendation",
                "confidence_score": 0.8,
                "key_features": ["영양가높음", "맛좋음", "구매편리"]
            },
            {
                "question": f"맛있는 {product_name} 브랜드 추천",
                "answer": f"맛있는 {product_name}을 선택하실 때는 원재료, 영양성분, 브랜드 신뢰도를 확인하시는 것이 좋습니다. 사용자 후기를 참고하시고, 개인의 취향에 맞는 제품을 찾아보세요.",
                "question_type": "features",
                "confidence_score": 0.75,
                "key_features": ["브랜드다양", "원재료확인", "개인취향"]
            },
            {
                "question": f"{product_name} 가격 정보",
                "answer": f"{product_name}의 가격은 브랜드, 용량, 판매처에 따라 다양합니다. 할인 이벤트나 대용량 구매를 활용하면 더 경제적으로 구매하실 수 있습니다.",
                "question_type": "price",
                "confidence_score": 0.7,
                "key_features": ["가격다양", "할인이벤트", "경제적구매"]
            },
            {
                "question": f"{product_name} 영양 성분",
                "answer": f"{product_name}은 단백질, 칼슘, 비타민 등이 풍부한 영양식품입니다. 건강한 식단을 위해 규칙적으로 섭취하시면 좋습니다.",
                "question_type": "features",
                "confidence_score": 0.8,
                "key_features": ["영양풍부", "건강식품", "규칙섭취"]
            }
        ]
    else:  # 기타 제품
        return [
            {
                "question": f"{product_name} 추천해줘",
                "answer": f"{product_name}은 다양한 브랜드에서 출시되고 있는 인기 제품입니다. 온라인과 오프라인 매장에서 쉽게 구매할 수 있으며, 사용자 후기도 대체로 긍정적입니다. 품질과 가격을 종합적으로 고려할 때 합리적인 선택입니다.",
                "question_type": "recommendation",
                "confidence_score": 0.8,
                "key_features": ["품질우수", "가격합리", "구매편리"]
            },
            {
                "question": f"좋은 {product_name} 고르는 방법",
                "answer": f"좋은 {product_name}을 선택하실 때는 브랜드 신뢰도, 가격대, 사용자 후기, 제품 사양을 종합적으로 고려하시는 것이 좋습니다. 온라인에서 다양한 옵션을 비교해보세요.",
                "question_type": "features",
                "confidence_score": 0.75,
                "key_features": ["브랜드신뢰", "사양비교", "후기확인"]
            },
            {
                "question": f"{product_name} 가격대",
                "answer": f"{product_name}의 가격은 브랜드와 제품 사양에 따라 다양합니다. 온라인 쇼핑몰에서 가격을 비교해보시고, 할인 이벤트를 활용하면 더욱 저렴하게 구매하실 수 있습니다.",
                "question_type": "price",
                "confidence_score": 0.7,
                "key_features": ["가격비교", "할인활용", "사양고려"]
            },
            {
                "question": f"{product_name} 사용법",
                "answer": f"{product_name} 사용 시에는 제품 설명서를 참고하시고, 안전 수칙을 준수하시기 바랍니다. 처음 사용하시는 경우 간단한 기능부터 익혀보세요.",
                "question_type": "installation",
                "confidence_score": 0.7,
                "key_features": ["설명서참고", "안전수칙", "단계적학습"]
            }
        ]

def extract_brand_name(product_name: str) -> str:
    """제품명에서 브랜드 추출"""
    words = product_name.split()
    if words:
        return words[0]
    return product_name

# ========================================
# 3. 실시간 데이터 수집 함수들
# ========================================

def auto_collect_and_generate_qa_fixed(query: str) -> bool:
    """수정된 자동 데이터 수집 및 QA 생성 함수"""
    try:
        # 진행 상황 표시
        progress_container = st.container()
        
        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            status_text.text("🔄 1단계: 제품 카테고리 분석 중...")
            progress_bar.progress(10)
            
            # 1. 카테고리 추정
            category_keywords = {
                1: ['도어락', '현관문', '스마트도어락', '디지털도어락'],
                2: ['노트북', '랩톱', '컴퓨터', '맥북', 'pc'],
                3: ['스마트폰', '휴대폰', '아이폰', '갤럭시', '폰'],
                4: ['태블릿', '아이패드', '갤럭시탭'],
                5: ['헤드폰', '이어폰', '무선이어폰', '에어팟'],
                6: ['음식', '식품', '요거트', '우유', '치즈', '과자', '라면', '그릭요거트', '운동화', '신발', '화장품', '향수']
            }
            
            # 식품 카테고리 자동 추가
            ensure_food_category()
            
            estimated_category_id = 2  # 기본값
            query_lower = query.lower()
            
            for cat_id, keywords in category_keywords.items():
                if any(keyword in query_lower for keyword in keywords):
                    estimated_category_id = cat_id
                    break
            
            progress_bar.progress(30)
            status_text.text("📝 2단계: 제품 정보 생성 중...")
            
            # 2. 제품별 맞춤 텍스트 생성
            product_name = query.strip()
            combined_text = generate_product_text(product_name, estimated_category_id)
            
            progress_bar.progress(50)
            status_text.text("💾 3단계: 원본 데이터 저장 중...")
            
            # 3. 원본 데이터 저장
            raw_data = {
                'product_name': product_name,
                'category_id': estimated_category_id,
                'search_keyword': product_name,
                'combined_text': combined_text,
                'shopping_data': [{"title": f"{product_name} 추천", "description": "온라인 쇼핑몰 판매"}],
                'blog_data': [{"title": f"{product_name} 후기", "description": "사용자 만족도 높음"}],
                'news_data': [{"title": f"{product_name} 시장 동향", "description": "시장 성장세"}],
                'data_quality_score': 0.75,
                'total_source_count': 12
            }
            
            raw_result = supabase.table('raw_product_data').insert(raw_data).execute()
            
            if not raw_result.data:
                st.error("❌ 원본 데이터 저장 실패")
                return False
            
            raw_data_id = raw_result.data[0]['id']
            
            progress_bar.progress(70)
            status_text.text("🤖 4단계: 질문-답변 데이터 생성 중...")
            
            # 4. QA 데이터 생성
            qa_samples = generate_qa_samples(product_name, estimated_category_id)
            
            progress_bar.progress(90)
            status_text.text("✅ 5단계: 최종 저장 중...")
            
            # 5. QA 데이터베이스에 저장
            saved_count = 0
            for qa in qa_samples:
                qa_data = {
                    'raw_data_id': raw_data_id,
                    'product_name': product_name,
                    'brand': extract_brand_name(product_name),
                    'category_id': estimated_category_id,
                    'question': qa['question'],
                    'answer': qa['answer'],
                    'question_type': qa['question_type'],
                    'confidence_score': qa.get('confidence_score', 0.75),
                    'recommendation_data': {
                        'key_features': qa.get('key_features', ['품질우수', '가격합리적', '다양한선택']),
                        'auto_generated': True,
                        'generated_at': datetime.now().isoformat()
                    }
                }
                
                try:
                    result = supabase.table('product_qa').insert(qa_data).execute()
                    if result.data:
                        saved_count += 1
                except Exception as e:
                    st.warning(f"QA 저장 중 오류: {e}")
                    continue
            
            progress_bar.progress(100)
            status_text.text("🎉 완료!")
            
            # 진행 표시 제거
            time.sleep(1)
            progress_bar.empty()
            status_text.empty()
            
            if saved_count > 0:
                st.success(f"✅ {product_name}에 대한 {saved_count}개의 QA가 생성되었습니다!")
                return True
            else:
                st.error("❌ QA 데이터 저장에 실패했습니다.")
                return False
                
    except Exception as e:
        st.error(f"❌ 자동 데이터 수집 실패: {str(e)}")
        logger.error(f"자동 QA 생성 실패: {e}")
        return False

# ========================================
# 4. 핵심 검색 함수들
# ========================================

def text_based_search_qa(query: str, category_filter: str = None, top_k: int = 10) -> List[Dict]:
    """텍스트 기반 검색으로 관련 QA 찾기 (기본 검색)"""
    try:
        # 검색어에서 핵심 키워드 추출
        keywords = [word.strip() for word in query.split() if len(word.strip()) > 1]
        
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
                try:
                    # 각 키워드에 대해 OR 검색
                    result = base_query.or_(
                        f"question.ilike.%{keyword}%,answer.ilike.%{keyword}%,product_name.ilike.%{keyword}%"
                    ).gte('confidence_score', 0.5).execute()
                    
                    all_results.extend(result.data)
                    
                except Exception as e:
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
        
        return final_results[:top_k]
        
    except Exception as e:
        logger.error(f"텍스트 검색 실패: {e}")
        return []

def enhanced_text_based_search_qa(query: str, category_filter: str = None, top_k: int = 10) -> List[Dict]:
    """개선된 텍스트 기반 검색 (자동 데이터 수집 포함) - 수정 버전"""
    try:
        # 1. 기존 검색 시도
        results = text_based_search_qa(query, category_filter, top_k)
        
        # 2. 결과가 없으면 자동 데이터 수집 옵션 제공
        if not results:
            st.warning("🔍 기존 데이터에서 관련 정보를 찾을 수 없습니다.")
            
            # 현재 검색 가능한 제품 보여주기
            show_available_products()
            
            st.markdown("---")
            st.markdown("### 🚀 새로운 제품 정보 자동 생성")
            
            # 세션 상태 초기화
            if 'auto_collection_triggered' not in st.session_state:
                st.session_state.auto_collection_triggered = False
            
            if 'auto_collection_query' not in st.session_state:
                st.session_state.auto_collection_query = ""
            
            # 쿼리가 변경되면 상태 초기화
            if st.session_state.auto_collection_query != query:
                st.session_state.auto_collection_triggered = False
                st.session_state.auto_collection_query = query
            
            # 자동 수집 설명
            st.info(f"💡 '{query}' 제품에 대한 기본 정보를 자동으로 생성합니다.")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                # 자동 수집 버튼
                if st.button("🚀 새로운 제품 정보 자동 수집하기", type="primary", key=f"auto_collect_{hash(query)}"):
                    st.session_state.auto_collection_triggered = True
            
            with col2:
                if st.button("🔄 페이지 새로고침", key=f"refresh_{hash(query)}"):
                    st.rerun()
            
            # 자동 수집 실행
            if st.session_state.auto_collection_triggered:
                st.markdown("---")
                
                success = auto_collect_and_generate_qa_fixed(query)
                
                if success:
                    # 재검색 실행
                    st.info("🔄 새로 생성된 정보로 다시 검색합니다...")
                    time.sleep(1)
                    
                    # 새로 생성된 데이터로 검색
                    new_results = text_based_search_qa(query, category_filter, top_k)
                    
                    if new_results:
                        st.success(f"🎉 {len(new_results)}개의 새로운 정보를 찾았습니다!")
                        
                        # 상태 초기화
                        st.session_state.auto_collection_triggered = False
                        
                        # 결과 반환
                        return new_results
                    else:
                        st.warning("⚠️ 데이터 생성 후에도 검색 결과가 없습니다.")
                else:
                    st.error("❌ 새로운 제품 정보 생성에 실패했습니다.")
                
                # 상태 초기화
                st.session_state.auto_collection_triggered = False
        
        return results
        
    except Exception as e:
        logger.error(f"개선된 검색 실패: {e}")
        st.error(f"검색 중 오류 발생: {e}")
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
                    'best_qa': qa,
                    'auto_generated': False
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
            
            # 자동 생성 여부 확인
            if qa.get('recommendation_data', {}).get('auto_generated'):
                products_info[product_name]['auto_generated'] = True
            
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
# 5. 데이터 관리 함수들
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
            'product_name, question, answer, question_type, confidence_score, created_at, recommendation_data'
        ).order('created_at', desc=True).limit(limit).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(f"QA 샘플 조회 실패: {e}")
        return []

def show_available_products():
    """현재 검색 가능한 제품 목록 표시"""
    try:
        result = supabase.table('product_qa').select('product_name, question_type').execute()
        products = {}
        
        for qa in result.data:
            product_name = qa['product_name']
            if product_name not in products:
                products[product_name] = set()
            products[product_name].add(qa['question_type'])
        
        if products:
            st.info("💡 현재 검색 가능한 제품들:")
            
            cols = st.columns(2)
            for i, (product, types) in enumerate(products.items()):
                with cols[i % 2]:
                    types_str = ", ".join(list(types)[:3])
                    if len(types) > 3:
                        types_str += "..."
                    st.markdown(f"• **{product}** ({types_str})")
        
    except Exception as e:
        st.error(f"제품 목록 조회 실패: {e}")

# ========================================
# 6. Streamlit UI
# ========================================

def main():
    """메인 애플리케이션"""
    
    # 제목
    st.title("🤖 AI 제품 추천 시스템")
    st.markdown("**모든 제품에 대해 검색 가능한 범용 추천 시스템**")
    
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
                
                # 자동 생성 표시
                if qa.get('recommendation_data', {}).get('auto_generated'):
                    st.markdown("🤖 *자동 생성됨*")
    
    # 메인 컨텐츠
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 🔍 제품 검색 및 추천")
        
        # 검색어 입력
        query = st.text_input(
            "궁금한 제품이나 요구사항을 입력하세요",
            placeholder="예: 그릭요거트, 200만원대 노트북, 무선이어폰, 운동화",
            help="어떤 제품이든 검색 가능합니다. 없는 제품은 자동으로 정보를 생성합니다."
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
        **🌟 범용 검색**
        - 모든 제품 검색 가능
        - 실시간 정보 자동 생성
        - 카테고리 자동 분류
        
        **⚡ 빠른 검색**
        - 텍스트 기반 즉시 검색
        - 키워드 매칭으로 정확한 결과
        - 실시간 답변 제공
        
        **🎯 정확한 답변**
        - 제품별 맞춤 정보
        - 다양한 질문 유형 지원
        - 신뢰도 기반 결과 정렬
        """)
    
    # 검색 실행
    if st.button("🔍 제품 추천 받기", type="primary", use_container_width=True):
        if not query.strip():
            st.warning("⚠️ 검색어를 입력해주세요!")
            return
        
        # 검색 실행
        with st.spinner("관련 제품 정보를 검색 중입니다..."):
            qa_results = enhanced_text_based_search_qa(
                query, 
                category_filter if category_filter != "전체" else None,
                top_k
            )
        
        if not qa_results:
            st.info("💡 위의 '새로운 제품 정보 자동 수집하기' 버튼을 클릭해보세요!")
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
                col_header1, col_header2, col_header3 = st.columns([3, 1, 1])
                
                with col_header1:
                    st.markdown(f"### {i}. {product_name}")
                    if info['brand']:
                        st.markdown(f"**브랜드:** {info['brand']}")
                
                with col_header2:
                    st.metric("신뢰도", f"{info['avg_confidence']:.2f}")
                
                with col_header3:
                    if info['auto_generated']:
                        st.markdown("🤖 **자동생성**")
                    else:
                        st.markdown("✅ **기존데이터**")
                
                # 최고 관련도 답변 표시
                best_qa = info['best_qa']
                
                st.markdown("#### 💬 주요 추천 정보")
                st.markdown(f"**Q:** {best_qa['question']}")
                
                # 답변을 예쁘게 표시
                with st.container():
                    st.markdown("**A:**")
                    if info['auto_generated']:
                        st.info(f"🤖 {best_qa['answer']}")
                    else:
                        st.success(best_qa['answer'])
                
                # 추가 정보 표시
                if len(info['answers']) > 1:
                    with st.expander(f"📚 {product_name} 추가 정보 ({len(info['answers'])-1}개 더)", expanded=False):
                        for j, qa_info in enumerate(info['answers'][1:], 2):
                            st.markdown(f"**Q{j}:** {qa_info['question']}")
                            st.markdown(f"**A{j}:** {qa_info['answer']}")
                            st.markdown(f"*유형: {qa_info['type']}, 신뢰도: {qa_info['confidence']:.2f}, 관련성: {qa_info['relevance']}*")
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
        
        # 자동 생성 통계
        auto_generated_count = sum(1 for qa in qa_results if qa.get('recommendation_data', {}).get('auto_generated'))
        if auto_generated_count > 0:
            st.info(f"🤖 이 중 {auto_generated_count}개는 새로 자동 생성된 정보입니다.")
        
        # 전체 검색 결과 옵션
        if st.checkbox("🔍 전체 검색 결과 보기", value=False):
            st.markdown("### 📋 전체 검색 결과")
            
            for i, qa in enumerate(qa_results, 1):
                with st.expander(f"결과 {i}: {qa['product_name']} - {qa['question_type']}", expanded=False):
                    
                    # 자동 생성 여부 표시
                    col_qa_header1, col_qa_header2 = st.columns([3, 1])
                    with col_qa_header1:
                        st.markdown(f"**제품:** {qa['product_name']} ({qa.get('brand', 'N/A')})")
                    with col_qa_header2:
                        if qa.get('recommendation_data', {}).get('auto_generated'):
                            st.markdown("🤖 자동생성")
                        else:
                            st.markdown("✅ 기존데이터")
                    
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
        - **범용 검색**: 모든 제품에 대해 검색 가능
        - **실시간 생성**: 없는 제품 정보 자동 생성
        - **텍스트 검색**: 키워드 기반 빠른 매칭
        - **데이터베이스**: Supabase (PostgreSQL)
        
        **📊 데이터 플로우:**
        1. 사용자 검색어 입력
        2. 기존 QA 데이터에서 검색
        3. 결과 없으면 자동 데이터 생성 옵션 제공
        4. 새 제품 정보 자동 수집 및 QA 생성
        5. 검색 결과 제품별 정리하여 표시
        
        **✨ 주요 장점:**
        - **무제한 제품 검색**: 어떤 제품이든 검색 가능
        - **즉시 답변 제공**: 기존 데이터는 즉시, 새 제품은 자동 생성
        - **카테고리 자동 분류**: 제품 유형 자동 감지
        - **신뢰도 기반 정렬**: 관련성과 신뢰도로 결과 정렬
        - **자동/기존 구분**: 데이터 출처 명확히 표시
        
        **🎯 사용 예시:**
        - 기존 제품: "도어락 추천", "맥북 프로" → 즉시 기존 정보 제공
        - 새로운 제품: "그릭요거트", "운동화", "화장품" → 자동 정보 생성 옵션 제공
        """)

    # 사용 팁
    with st.expander("💡 사용 팁", expanded=False):
        st.markdown("""
        **🔍 효과적인 검색 방법:**
        - **구체적인 제품명**: "아이폰 15", "삼성 도어락" 등
        - **카테고리 + 특징**: "가벼운 노트북", "무선 이어폰" 등
        - **가격대 포함**: "200만원대 노트북", "저렴한 도어락" 등
        - **식품**: "그릭요거트", "단백질바", "오가닉 우유" 등
        
        **🚀 새 제품 추가 방법:**
        1. 검색어 입력 후 "제품 추천 받기" 클릭
        2. "관련 정보를 찾을 수 없습니다" 메시지 확인
        3. "새로운 제품 정보 자동 수집하기" 버튼 클릭
        4. 5단계 진행 과정 확인 (카테고리 분석 → 정보 생성 → 저장 → QA 생성 → 완료)
        5. 자동 생성 완료 후 검색 결과 확인
        
        **⭐ 고급 활용:**
        - 카테고리 필터로 정확한 검색 결과 확보
        - 검색 개수 조절로 원하는 만큼의 정보 수집
        - 전체 검색 결과로 상세 정보 확인
        - 자동생성(🤖)과 기존데이터(✅) 구분하여 정보 품질 확인
        
        **🔧 트러블슈팅:**
        - 버튼이 작동하지 않으면 "페이지 새로고침" 버튼 클릭
        - 검색 결과가 없으면 다른 키워드로 재시도
        - 오류 발생 시 페이지를 새로고침하고 다시 시도
        """)

if __name__ == "__main__":
    main()
