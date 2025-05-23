"""
완전한 도어락 추천 Streamlit 앱
GitHub Secrets에서 API 키를 읽어와서 네이버 API 데이터 수집 및 추천 시스템 구현
"""

import streamlit as st
import os
import json
import urllib.request
import urllib.parse
import re
import time
import hashlib
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
import logging

from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 페이지 설정
st.set_page_config(
    page_title="🔐 스마트 도어락 추천 시스템",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================================
# 1. 설정 및 초기화
# ========================================

@st.cache_resource
def init_clients():
    """클라이언트 초기화 (GitHub Secrets 또는 Streamlit Secrets 사용)"""
    try:
        # GitHub Actions 환경에서는 os.environ, Streamlit Cloud에서는 st.secrets 사용
        if hasattr(st, 'secrets') and 'SUPABASE_URL' in st.secrets:
            # Streamlit Secrets 사용
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
            naver_client_id = st.secrets["NAVER_CLIENT_ID"]
            naver_client_secret = st.secrets["NAVER_CLIENT_SECRET"]
        else:
            # 환경 변수 사용 (GitHub Actions)
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            naver_client_id = os.environ.get("NAVER_CLIENT_ID")
            naver_client_secret = os.environ.get("NAVER_CLIENT_SECRET")
        
        # API 키 확인
        if not all([supabase_url, supabase_key, naver_client_id, naver_client_secret]):
            st.error("❌ API 키가 설정되지 않았습니다. GitHub Secrets 또는 Streamlit Secrets를 확인해주세요.")
            st.stop()
        
        # 클라이언트 초기화
        supabase = create_client(supabase_url, supabase_key)
        
        return supabase, naver_client_id, naver_client_secret
        
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
supabase, naver_client_id, naver_client_secret = init_clients()
embedding_model = load_embedding_model()

# ========================================
# 2. 핵심 기능 함수들
# ========================================

def generate_embedding(text: str) -> Optional[List[float]]:
    """텍스트 임베딩 생성 (768차원 → 1536차원 패딩)"""
    if not embedding_model or not text or len(text.strip()) < 5:
        return None
    
    try:
        cleaned_text = re.sub(r'\s+', ' ', text.strip())
        cleaned_text = re.sub(r'[^\w\s가-힣\.]', ' ', cleaned_text)[:512]
        
        embedding = embedding_model.encode(cleaned_text, convert_to_tensor=False)
        embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        
        # 768차원을 1536차원으로 패딩
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
        logger.error(f"임베딩 생성 실패: {e}")
        return None

def search_naver_api(keyword: str, source_type: str, display: int = 100) -> List[Dict]:
    """네이버 API 검색"""
    endpoint_map = {"쇼핑": "shop", "블로그": "blog", "뉴스": "news"}
    endpoint = endpoint_map.get(source_type)
    
    if not endpoint:
        return []
    
    try:
        # 소스별 맞춤 검색어
        if source_type == "쇼핑":
            search_query = keyword
        elif source_type == "블로그":
            search_query = f"{keyword} 후기 설치"
        else:  # 뉴스
            search_query = f"{keyword} 보안 해킹"
        
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://openapi.naver.com/v1/search/{endpoint}?query={encoded_query}&display={display}&sort=sim"
        
        request = urllib.request.Request(url)
        request.add_header("X-Naver-Client-Id", naver_client_id)
        request.add_header("X-Naver-Client-Secret", naver_client_secret)
        
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.getcode() == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('items', [])
            else:
                return []
                
    except Exception as e:
        logger.error(f"네이버 API 검색 실패 ({source_type}): {e}")
        return []

def process_and_save_data(keyword: str) -> Dict[str, int]:
    """네이버 API 데이터 수집 및 저장"""
    results = {"쇼핑": 0, "블로그": 0, "뉴스": 0}
    
    for source_type in ["쇼핑", "블로그", "뉴스"]:
        # API 검색
        items = search_naver_api(keyword, source_type)
        saved_count = 0
        
        for item in items:
            try:
                # 데이터 처리
                if source_type == "쇼핑":
                    processed_data = process_shopping_item(item)
                elif source_type == "블로그":
                    processed_data = process_blog_item(item)
                else:  # 뉴스
                    processed_data = process_news_item(item)
                
                if processed_data and save_to_database(processed_data):
                    saved_count += 1
                    
            except Exception as e:
                continue
        
        results[source_type] = saved_count
        time.sleep(0.5)  # API 호출 제한 고려
    
    return results

def process_shopping_item(item: Dict) -> Dict:
    """쇼핑 아이템 처리"""
    title = re.sub('<[^<]+?>', '', item.get('title', ''))
    description = re.sub('<[^<]+?>', '', item.get('description', ''))
    
    content = f"상품명: {title}\n설명: {description}\n브랜드: {item.get('brand', '')}\n가격: {item.get('lprice', '')}원"
    
    return {
        'title': title,
        'content': content,
        'url': item.get('link', ''),
        'source_type': '쇼핑',
        'brand': item.get('brand', ''),
        'price_min': int(item.get('lprice', 0)) if item.get('lprice') else None,
        'price_max': int(item.get('hprice', 0)) if item.get('hprice') else None,
        'mall_name': item.get('mallName', ''),
        'source_metadata': item,
        'embedding': generate_embedding(content),
        # 추가 정보
        'rating': None,  # 네이버 쇼핑은 평점 정보가 API에 없음
        'image_url': item.get('image', ''),
        'product_id': item.get('productId', '')
    }

def process_blog_item(item: Dict) -> Dict:
    """블로그 아이템 처리"""
    title = re.sub('<[^<]+?>', '', item.get('title', ''))
    description = re.sub('<[^<]+?>', '', item.get('description', ''))
    
    content = f"제목: {title}\n내용: {description}\n블로거: {item.get('bloggername', '')}"
    
    pub_date = None
    if item.get('postdate'):
        try:
            pub_date = datetime.strptime(item['postdate'], '%Y%m%d').date()
        except:
            pass
    
    return {
        'title': title,
        'content': content,
        'url': item.get('link', ''),
        'source_type': '블로그',
        'pub_date': pub_date,
        'blogger_name': item.get('bloggername', ''),
        'source_metadata': item,
        'embedding': generate_embedding(content)
    }

def process_news_item(item: Dict) -> Dict:
    """뉴스 아이템 처리"""
    title = re.sub('<[^<]+?>', '', item.get('title', ''))
    description = re.sub('<[^<]+?>', '', item.get('description', ''))
    
    content = f"뉴스 제목: {title}\n내용: {description}"
    
    pub_date = None
    if item.get('pubDate'):
        try:
            pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S %z').date()
        except:
            pass
    
    publisher = ""
    if item.get('originallink'):
        try:
            publisher = item['originallink'].replace('https://', '').replace('http://', '').split('/')[0]
        except:
            pass
    
    return {
        'title': title,
        'content': content,
        'url': item.get('link', ''),
        'source_type': '뉴스',
        'pub_date': pub_date,
        'publisher': publisher,
        'source_metadata': item,
        'embedding': generate_embedding(content)
    }

def save_to_database(processed_data: Dict) -> bool:
    """데이터베이스에 저장"""
    try:
        # 중복 확인
        existing = supabase.table('documents').select('id').eq('url', processed_data['url']).execute()
        
        if existing.data:
            return False  # 이미 존재
        
        # documents 테이블에 저장
        doc_data = {
            'title': processed_data['title'],
            'content': processed_data['content'],
            'url': processed_data['url'],
            'source_type': processed_data['source_type'],
            'embedding': processed_data.get('embedding'),
            'source_metadata': processed_data['source_metadata'],
            'brand': processed_data.get('brand'),
            'price_min': processed_data.get('price_min'),
            'price_max': processed_data.get('price_max'),
            'pub_date': processed_data.get('pub_date').isoformat() if processed_data.get('pub_date') else None,
            'publisher': processed_data.get('publisher'),
            'blogger_name': processed_data.get('blogger_name'),
            'mall_name': processed_data.get('mall_name')
        }
        
        result = supabase.table('documents').insert(doc_data).execute()
        document_id = result.data[0]['id']
        
        # 소스별 특화 테이블에 저장
        if processed_data['source_type'] == '쇼핑':
            save_product_data(document_id, processed_data)
        elif processed_data['source_type'] == '블로그':
            save_blog_data(document_id, processed_data)
        elif processed_data['source_type'] == '뉴스':
            save_news_data(document_id, processed_data)
        
        return True
        
    except Exception as e:
        logger.error(f"데이터베이스 저장 실패: {e}")
        return False

def save_product_data(document_id: int, processed_data: Dict):
    """products 테이블에 저장"""
    try:
        product_data = {
            'document_id': document_id,
            'product_name': processed_data['title'],
            'brand': processed_data.get('brand'),
            'lprice': processed_data.get('price_min'),
            'hprice': processed_data.get('price_max'),
            'mall_name': processed_data.get('mall_name'),
            'product_id': processed_data.get('product_id'),
            'image_url': processed_data.get('image_url'),
            'product_specs': processed_data['source_metadata'],
            'rating': processed_data.get('rating', 0.0),
            'review_count': 0
        }
        supabase.table('products').insert(product_data).execute()
    except Exception as e:
        logger.debug(f"제품 데이터 저장 실패: {e}")

def save_blog_data(document_id: int, processed_data: Dict):
    """blog_posts 테이블에 저장"""
    try:
        blog_data = {
            'document_id': document_id,
            'blogger_name': processed_data.get('blogger_name'),
            'blogger_id': processed_data['source_metadata'].get('bloggername'),
            'blog_url': processed_data['source_metadata'].get('bloggerlink'),
            'post_date': processed_data.get('pub_date').isoformat() if processed_data.get('pub_date') else None,
            'review_type': 'product_review'
        }
        supabase.table('blog_posts').insert(blog_data).execute()
    except Exception as e:
        logger.debug(f"블로그 데이터 저장 실패: {e}")

def save_news_data(document_id: int, processed_data: Dict):
    """news_articles 테이블에 저장"""
    try:
        keywords = [word for word in processed_data['title'].split() if len(word) > 2][:10]
        
        news_data = {
            'document_id': document_id,
            'publisher': processed_data.get('publisher'),
            'original_url': processed_data['source_metadata'].get('originallink'),
            'pub_date': processed_data.get('pub_date').isoformat() if processed_data.get('pub_date') else None,
            'article_type': 'analysis',
            'keywords': keywords
        }
        supabase.table('news_articles').insert(news_data).execute()
    except Exception as e:
        logger.debug(f"뉴스 데이터 저장 실패: {e}")

def get_doorlock_recommendations(query: str = "도어락") -> List[Dict]:
    """도어락 추천 결과 조회"""
    try:
        result = supabase.rpc('get_doorlock_recommendations', {'query_text': query}).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"추천 결과 조회 실패: {e}")
        return []

def create_sample_product_data():
    """샘플 제품 데이터 생성 (AI 특징 점수 포함)"""
    try:
        # 기존 product_master에 AI 분석 결과 추가
        sample_products = [
            {
                'canonical_name': '삼성 SHP-DP930',
                'features': {'설치_간편성': 4.2, '보안성': 3.8, '가격_경쟁력': 3.5, '사용자_만족도': 4.0}
            },
            {
                'canonical_name': '게이트맨 F50', 
                'features': {'설치_간편성': 3.5, '보안성': 4.9, '가격_경쟁력': 4.2, '사용자_만족도': 4.3}
            },
            {
                'canonical_name': 'LG 스마트 도어락',
                'features': {'설치_간편성': 3.8, '보안성': 4.1, '가격_경쟁력': 3.8, '사용자_만족도': 3.9}
            }
        ]
        
        for product in sample_products:
            # product_master 조회
            master_result = supabase.table('product_master').select('id').eq('canonical_name', product['canonical_name']).execute()
            
            if master_result.data:
                master_id = master_result.data[0]['id']
                
                # product_mentions에 AI 분석 결과 저장
                mention_data = {
                    'product_master_id': master_id,
                    'product_name': product['canonical_name'],
                    'brand': product['canonical_name'].split()[0],
                    'mention_type': 'main_product',
                    'sentiment': 'positive',
                    'confidence_score': 0.9,
                    'feature_scores': product['features'],
                    'mention_context': f"{product['canonical_name']} 제품 분석 결과"
                }
                
                supabase.table('product_mentions').insert(mention_data).execute()
        
        # product_master 점수 업데이트
        supabase.rpc('update_product_master_scores').execute()
        
    except Exception as e:
        logger.error(f"샘플 데이터 생성 실패: {e}")

# ========================================
# 3. Streamlit UI
# ========================================

def main():
    """메인 애플리케이션"""
    
    # 제목
    st.title("🔐 스마트 도어락 추천 시스템")
    st.markdown("**AI가 네이버 쇼핑, 블로그, 뉴스를 분석하여 최적의 도어락을 추천해드립니다.**")
    
    # 사이드바
    with st.sidebar:
        st.title("⚙️ 설정")
        
        # 데이터베이스 상태
        st.markdown("### 📊 데이터베이스 현황")
        try:
            # 문서 수 조회
            docs_result = supabase.table('documents').select('id', count='exact').execute()
            total_docs = docs_result.count if hasattr(docs_result, 'count') else len(docs_result.data)
            
            st.metric("총 문서 수", f"{total_docs:,}개")
            
            # 제품 수 조회
            products_result = supabase.table('product_master').select('id', count='exact').execute()
            total_products = products_result.count if hasattr(products_result, 'count') else len(products_result.data)
            
            st.metric("등록 제품 수", f"{total_products:,}개")
            
        except Exception as e:
            st.error("DB 연결 오류")
        
        st.markdown("---")
        
        # 샘플 데이터 생성 버튼
        if st.button("🎯 샘플 데이터 생성", help="테스트용 샘플 데이터를 생성합니다"):
            with st.spinner("샘플 데이터 생성 중..."):
                create_sample_product_data()
                st.success("✅ 샘플 데이터 생성 완료!")
                st.rerun()
    
    # 메인 컨텐츠
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 🔍 도어락 검색 및 추천")
        
        # 검색어 입력
        query = st.text_input(
            "궁금한 것을 물어보세요",
            placeholder="도어락 추천해줘",
            help="예: 도어락 추천해줘, 설치 간단한 도어락, 보안 좋은 도어락"
        )
        
        # 검색 옵션
        col_search1, col_search2 = st.columns(2)
        
        with col_search1:
            search_mode = st.selectbox(
                "검색 모드",
                ["기존 데이터 검색", "새 데이터 수집 후 검색"],
                help="기존 데이터로 빠른 검색 또는 최신 데이터 수집 후 검색"
            )
        
        with col_search2:
            collect_sources = st.multiselect(
                "수집 소스 (새 데이터 수집 시)",
                ["쇼핑", "블로그", "뉴스"],
                default=["쇼핑", "블로그", "뉴스"]
            )
    
    with col2:
        st.markdown("### 💡 추천 시스템 특징")
        st.markdown("""
        **🛍️ 종합 분석**
        - 가격 정보 (쇼핑)
        - 사용자 후기 (블로그)  
        - 보안 뉴스 (뉴스)
        
        **🤖 AI 평가**
        - 설치 간편성
        - 보안성
        - 가격 경쟁력
        - 사용자 만족도
        """)
    
    # 검색 실행
    if st.button("🔍 도어락 추천 받기", type="primary", use_container_width=True):
        if not query.strip():
            st.warning("⚠️ 검색어를 입력해주세요!")
            return
        
        # 새 데이터 수집 모드
        if search_mode == "새 데이터 수집 후 검색" and collect_sources:
            st.markdown("### 📡 데이터 수집 중...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("네이버 API에서 데이터 수집 중..."):
                try:
                    results = process_and_save_data(query)
                    
                    progress_bar.progress(100)
                    
                    # 수집 결과 표시
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("🛍️ 쇼핑", f"{results['쇼핑']}개")
                    with col2:
                        st.metric("✍️ 블로그", f"{results['블로그']}개")
                    with col3:
                        st.metric("📰 뉴스", f"{results['뉴스']}개")
                    
                    st.success(f"✅ 총 {sum(results.values())}개 데이터 수집 완료!")
                    
                except Exception as e:
                    st.error(f"❌ 데이터 수집 실패: {str(e)}")
                    return
                finally:
                    progress_bar.empty()
                    status_text.empty()
        
        # 추천 결과 조회 및 표시
        st.markdown("### 🎯 도어락 추천 결과")
        
        with st.spinner("AI가 추천 결과를 분석 중..."):
            try:
                recommendations = get_doorlock_recommendations(query)
                
                if not recommendations:
                    st.warning("⚠️ 추천 결과를 찾을 수 없습니다. 새 데이터 수집을 시도해보세요.")
                    return
                
                # 추천 결과를 타입별로 분류
                installation_recs = [r for r in recommendations if r['recommendation_type'] == '설치 간편성 기준 추천']
                security_recs = [r for r in recommendations if r['recommendation_type'] == '보안성 기준 추천']
                
                # 설치 간편성 기준 추천
                if installation_recs:
                    st.markdown("#### 🔧 설치 간편성 기준 추천:")
                    
                    for i, rec in enumerate(installation_recs, 1):
                        with st.container():
                            st.markdown(f"**{i}. {rec['product_name']}**")
                            
                            col1, col2 = st.columns([1, 1])
                            
                            with col1:
                                st.markdown(f"• **쇼핑**: {rec['price_info']}, {rec['rating_info']}")
                                
                                # 블로그 후기
                                if rec['blog_quotes']:
                                    quotes = [q for q in rec['blog_quotes'] if q and len(q) > 5]
                                    if quotes:
                                        st.markdown(f"• **블로그 후기**: \"{quotes[0][:50]}...\"")
                            
                            with col2:
                                st.markdown(f"• **{rec['score_display']}**")
                                st.markdown(f"• **{rec['star_rating']}** ({rec['star_rating'].count('⭐')}/5)")
                            
                            st.markdown("---")
                
                # 보안성 기준 추천  
                if security_recs:
                    st.markdown("#### 🔒 보안성 기준 추천:")
                    
                    for i, rec in enumerate(security_recs, 1):
                        with st.container():
                            st.markdown(f"**{i}. {rec['product_name']}**")
                            
                            col1, col2 = st.columns([1, 1])
                            
                            with col1:
                                # 뉴스 하이라이트
                                if rec['news_highlights']:
                                    highlights = [h for h in rec['news_highlights'] if h]
                                    if highlights:
                                        st.markdown(f"• **뉴스**: \"{highlights[0]}\"")
                                
                                # 블로그 후기
                                if rec['blog_quotes']:
                                    quotes = [q for q in rec['blog_quotes'] if q and len(q) > 5]
                                    if quotes:
                                        st.markdown(f"• **블로그**: \"{quotes[0][:50]}...\"")
                            
                            with col2:
                                st.markdown(f"• **{rec['score_display']}**")
                                st.markdown(f"• **{rec['star_rating']}** ({rec['star_rating'].count('⭐')}/5)")
                            
                            st.markdown("---")
                
            except Exception as e:
                st.error(f"❌ 추천 결과 조회 실패: {str(e)}")
                st.info("💡 샘플 데이터 생성 버튼을 눌러 테스트 데이터를 만들어보세요.")

    # 하단 정보
    st.markdown("---")
    with st.expander("ℹ️ 시스템 정보", expanded=False):
        st.markdown("""
        **🔧 기술 스택:**
        - **Frontend**: Streamlit
        - **Database**: Supabase (PostgreSQL + pgvector)
        - **AI/ML**: SentenceTransformer, OpenAI
        - **API**: 네이버 검색 API
        
        **📊 데이터 소스:**
        - 네이버 쇼핑: 제품 정보, 가격, 스펙
        - 네이버 블로그: 사용자 후기, 설치 경험
        - 네이버 뉴스: 보안 이슈, 업계 동향
        
        **🤖 AI 분석:**
        - 설치 간편성 (1-5점)
        - 보안성 (1-5점) 
        - 가격 경쟁력 (1-5점)
        - 사용자 만족도 (1-5점)
        """)

if __name__ == "__main__":
    main()
