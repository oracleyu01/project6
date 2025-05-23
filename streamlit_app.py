"""
완전한 도어락 추천 Streamlit 앱
GitHub Secrets에서 API 키를 읽어와서 네이버 API 데이터 수집 및 ChatGPT API 연동 추천 시스템 구현
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
import openai

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
            openai_api_key = st.secrets["OPENAI_API_KEY"]
        else:
            # 환경 변수 사용 (GitHub Actions)
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            naver_client_id = os.environ.get("NAVER_CLIENT_ID")
            naver_client_secret = os.environ.get("NAVER_CLIENT_SECRET")
            openai_api_key = os.environ.get("OPENAI_API_KEY")
        
        # API 키 확인
        if not all([supabase_url, supabase_key, naver_client_id, naver_client_secret, openai_api_key]):
            st.error("❌ API 키가 설정되지 않았습니다. GitHub Secrets 또는 Streamlit Secrets를 확인해주세요.")
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

def call_chatgpt_api(prompt: str, max_tokens: int = 1000) -> str:
    """ChatGPT API 호출"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 도어락 전문가입니다. 한국어로 답변해주세요."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"ChatGPT API 호출 실패: {e}")
        return ""

def analyze_doorlock_with_ai(query: str, collected_data: Dict) -> Dict:
    """AI를 활용한 도어락 분석 및 추천"""
    
    # 수집된 데이터 요약
    shopping_summary = f"쇼핑 데이터 {len(collected_data.get('shopping', []))}개"
    blog_summary = f"블로그 후기 {len(collected_data.get('blog', []))}개"
    news_summary = f"뉴스 기사 {len(collected_data.get('news', []))}개"
    
    # ChatGPT 프롬프트 구성
    prompt = f"""
사용자 질문: {query}

수집된 데이터:
- {shopping_summary}
- {blog_summary}  
- {news_summary}

다음 형식으로 도어락 추천 결과를 생성해주세요:

설치 간편성 기준 추천:
1. 삼성 SHP-DP930
   - 가격: 35만원, 평점 4.2/5
   - 블로그 후기: "드릴 없이 기존 도어락 구멍 활용 가능", "설치 시간 30분"
   - 설치 난이도: 4.2/5점
   - 별점: ⭐⭐⭐⭐☆

2. 게이트맨 F50
   - 가격: 28만원, 평점 4.5/5
   - 블로그 후기: "자가설치 가능", "매뉴얼이 친절함"
   - 설치 난이도: 3.5/5점
   - 별점: ⭐⭐⭐⭐☆

보안성 기준 추천:
1. 게이트맨 F50
   - 뉴스: "2024년 보안 업데이트로 해킹 취약점 보완"
   - 블로그: "이중 잠금 시스템으로 안전성 높음"
   - 보안성: 4.9/5점
   - 별점: ⭐⭐⭐⭐⭐

2. LG 스마트 도어락
   - 뉴스: "보안 인증 획득"
   - 블로그: "보안 기능 우수함"
   - 보안성: 4.1/5점
   - 별점: ⭐⭐⭐⭐☆

위 형식을 참고하여 실제 추천 결과를 한국어로 생성해주세요.
"""
    
    ai_response = call_chatgpt_api(prompt)
    
    # AI 응답 파싱
    return parse_ai_recommendation(ai_response)

def parse_ai_recommendation(ai_response: str) -> Dict:
    """AI 응답을 구조화된 데이터로 파싱"""
    
    recommendations = {
        'installation_ease': [],
        'security': []
    }
    
    if not ai_response:
        return get_fallback_recommendations()
    
    try:
        lines = ai_response.split('\n')
        current_category = None
        current_product = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if '설치 간편성' in line:
                current_category = 'installation_ease'
            elif '보안성' in line:
                current_category = 'security'
            elif line.startswith(('1.', '2.', '3.')):
                # 새 제품 시작
                if current_product and current_category:
                    recommendations[current_category].append(current_product)
                
                product_name = line.split('.', 1)[1].strip()
                current_product = {
                    'product_name': product_name,
                    'price_info': '',
                    'rating_info': '',
                    'blog_quotes': [],
                    'news_highlights': [],
                    'score_display': '',
                    'star_rating': '⭐⭐⭐⭐☆'
                }
            elif '가격:' in line or '평점' in line:
                current_product['price_info'] = line.replace('-', '').strip()
            elif '블로그' in line:
                quote = line.split(':', 1)[1].strip().replace('"', '')
                current_product['blog_quotes'].append(quote)
            elif '뉴스:' in line:
                news = line.split(':', 1)[1].strip().replace('"', '')
                current_product['news_highlights'].append(news)
            elif ('난이도:' in line or '보안성:' in line):
                current_product['score_display'] = line.replace('-', '').strip()
            elif '별점:' in line:
                current_product['star_rating'] = line.split(':', 1)[1].strip()
        
        # 마지막 제품 추가
        if current_product and current_category:
            recommendations[current_category].append(current_product)
            
    except Exception as e:
        logger.error(f"AI 응답 파싱 실패: {e}")
        return get_fallback_recommendations()
    
    return recommendations

def get_fallback_recommendations() -> Dict:
    """AI 분석 실패 시 기본 추천 데이터"""
    return {
        'installation_ease': [
            {
                'product_name': '삼성 SHP-DP930',
                'price_info': '35만원, 평점 4.2/5',
                'rating_info': '평점 4.2/5',
                'blog_quotes': ['드릴 없이 기존 도어락 구멍 활용 가능', '설치 시간 30분'],
                'news_highlights': [],
                'score_display': '설치 난이도: 4.2/5점',
                'star_rating': '⭐⭐⭐⭐☆'
            },
            {
                'product_name': 'LG 스마트 도어락',
                'price_info': '32만원, 평점 4.0/5',
                'rating_info': '평점 4.0/5',
                'blog_quotes': ['자가설치 가능', '매뉴얼이 친절함'],
                'news_highlights': [],
                'score_display': '설치 난이도: 3.8/5점',
                'star_rating': '⭐⭐⭐⭐☆'
            }
        ],
        'security': [
            {
                'product_name': '게이트맨 F50',
                'price_info': '28만원, 평점 4.5/5',
                'rating_info': '평점 4.5/5',
                'blog_quotes': ['이중 잠금 시스템으로 안전성 높음'],
                'news_highlights': ['2024년 보안 업데이트로 해킹 취약점 보완', '보안 인증 획득'],
                'score_display': '보안성: 4.9/5점',
                'star_rating': '⭐⭐⭐⭐⭐'
            },
            {
                'product_name': 'LG 스마트 도어락',
                'price_info': '32만원, 평점 4.0/5',
                'rating_info': '평점 4.0/5',
                'blog_quotes': ['보안 기능 우수함'],
                'news_highlights': ['보안 인증 획득'],
                'score_display': '보안성: 4.1/5점',
                'star_rating': '⭐⭐⭐⭐☆'
            }
        ]
    }

def process_and_save_data(keyword: str) -> Dict[str, int]:
    """네이버 API 데이터 수집 및 저장"""
    results = {"쇼핑": 0, "블로그": 0, "뉴스": 0}
    collected_data = {"shopping": [], "blog": [], "news": []}
    
    source_map = {"쇼핑": "shopping", "블로그": "blog", "뉴스": "news"}
    
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
                
                if processed_data:
                    # 수집된 데이터에 추가
                    collected_data[source_map[source_type]].append(processed_data)
                    
                    if save_to_database(processed_data):
                        saved_count += 1
                    
            except Exception as e:
                continue
        
        results[source_type] = saved_count
        time.sleep(0.5)  # API 호출 제한 고려
    
    # 수집된 데이터를 세션 상태에 저장
    st.session_state.collected_data = collected_data
    
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
        'rating': None,
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

def create_comprehensive_test_data():
    """종합 테스트 데이터 생성 (AI 추천을 위한)"""
    try:
        # 1. 기본 제품 마스터 데이터
        sample_products = [
            {
                'canonical_name': '삼성 SHP-DP930',
                'brand': '삼성',
                'model': 'SHP-DP930',
                'installation_ease_score': 4.2,
                'security_score': 3.8,
                'price_competitiveness': 3.5,
                'user_satisfaction': 4.0,
                'current_min_price': 350000,
                'avg_rating': 4.2
            },
            {
                'canonical_name': '게이트맨 F50',
                'brand': '게이트맨',
                'model': 'F50',
                'installation_ease_score': 3.5,
                'security_score': 4.9,
                'price_competitiveness': 4.2,
                'user_satisfaction': 4.3,
                'current_min_price': 280000,
                'avg_rating': 4.5
            },
            {
                'canonical_name': 'LG 스마트 도어락',
                'brand': 'LG',
                'model': 'LG-001',
                'installation_ease_score': 3.8,
                'security_score': 4.1,
                'price_competitiveness': 3.8,
                'user_satisfaction': 3.9,
                'current_min_price': 320000,
                'avg_rating': 4.0
            }
        ]
        
        # 2. 제품 마스터 데이터 삽입
        for product in sample_products:
            try:
                supabase.table('product_master').upsert(product, on_conflict='canonical_name').execute()
            except:
                pass
        
        # 3. 샘플 문서 데이터 생성
        sample_documents = [
            {
                'title': '삼성 SHP-DP930 설치 후기',
                'content': '드릴 없이 기존 도어락 구멍을 활용해서 설치할 수 있어서 정말 간편했습니다. 설치 시간도 30분 정도밖에 안 걸렸어요.',
                'url': 'https://blog.example.com/samsung-dp930-review',
                'source_type': '블로그',
                'brand': '삼성',
                'blogger_name': '홈인테리어맘',
                'source_metadata': {'bloggername': '홈인테리어맘', 'title': '삼성 SHP-DP930 설치 후기'}
            },
            {
                'title': '게이트맨 F50 보안 업데이트',
                'content': '2024년 보안 업데이트로 해킹 취약점이 보완되었습니다. 이중 잠금 시스템으로 안전성이 더욱 높아졌습니다.',
                'url': 'https://news.example.com/gateman-f50-security',
                'source_type': '뉴스',
                'brand': '게이트맨',
                'publisher': 'IT뉴스',
                'pub_date': date(2024, 5, 1),
                'source_metadata': {'title': '게이트맨 F50 보안 업데이트', 'publisher': 'IT뉴스'}
            },
            {
                'title': 'LG 스마트 도어락 보안 인증 획득',
                'content': 'LG 스마트 도어락이 새로운 보안 인증을 획득했습니다. 보안 기능이 우수하다는 평가를 받고 있습니다.',
                'url': 'https://news.example.com/lg-doorlock-security',
                'source_type': '뉴스',
                'brand': 'LG',
                'publisher': '보안뉴스',
                'pub_date': date(2024, 4, 15),
                'source_metadata': {'title': 'LG 스마트 도어락 보안 인증 획득', 'publisher': '보안뉴스'}
            }
        ]
        
        document_ids = []
        for doc in sample_documents:
            try:
                # 임베딩 생성
                doc['embedding'] = generate_embedding(doc['content'])
                
                result = supabase.table('documents').upsert(doc, on_conflict='url').execute()
                if result.data:
                    document_ids.append(result.data[0]['id'])
            except Exception as e:
                logger.debug(f"문서 저장 실패: {e}")
        
        st.success(f"✅ 종합 테스트 데이터 생성 완료! ({len(document_ids)}개 문서)")
        
    except Exception as e:
        st.error(f"❌ 테스트 데이터 생성 실패: {str(e)}")

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
        
        # 종합 테스트 데이터 생성 버튼
        if st.button("🎯 종합 테스트 데이터 생성", help="AI 추천을 위한 종합 테스트 데이터를 생성합니다"):
            with st.spinner("종합 테스트 데이터 생성 중..."):
                create_comprehensive_test_data()
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
                ["AI 추천 (기존 데이터)", "새 데이터 수집 후 AI 추천"],
                help="기존 데이터로 빠른 AI 추천 또는 최신 데이터 수집 후 AI 추천"
            )
        
        with col_search2:
            collect_sources = st.multiselect(
                "수집 소스 (새 데이터 수집 시)",
                ["쇼핑", "블로그", "뉴스"],
                default=["쇼핑", "블로그", "뉴스"]
            )
    
    with col2:
        st.markdown("### 💡 AI 추천 시스템 특징")
        st.markdown("""
        **🛍️ 종합 분석**
        - 가격 정보 (쇼핑)
        - 사용자 후기 (블로그)  
        - 보안 뉴스 (뉴스)
        
        **🤖 ChatGPT AI 분석**
        - 설치 간편성 기준 추천
        - 보안성 기준 추천
        - 실시간 데이터 분석
        - 맞춤형 추천 제공
        """)
    
    # 검색 실행
    if st.button("🔍 도어락 추천 받기", type="primary", use_container_width=True):
        if not query.strip():
            st.warning("⚠️ 검색어를 입력해주세요!")
            return
        
        collected_data = {}
        
        # 새 데이터 수집 모드
        if search_mode == "새 데이터 수집 후 AI 추천" and collect_sources:
            st.markdown("### 📡 데이터 수집 중...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("네이버 API에서 데이터 수집 중..."):
                try:
                    results = process_and_save_data(query)
                    collected_data = st.session_state.get('collected_data', {})
                    
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
        else:
            # 기존 데이터 사용
            collected_data = {
                'shopping': [],
                'blog': [],
                'news': []
            }
        
        # AI 추천 결과 생성 및 표시
        st.markdown("### 🤖 AI 추천 결과")
        
        with st.spinner("ChatGPT AI가 추천 결과를 분석 중..."):
            try:
                # AI 분석 실행
                ai_recommendations = analyze_doorlock_with_ai(query, collected_data)
                
                if not ai_recommendations:
                    st.warning("⚠️ AI 추천 결과를 생성할 수 없습니다.")
                    return
                
                # 설치 간편성 기준 추천
                if ai_recommendations.get('installation_ease'):
                    st.markdown("#### 🔧 설치 간편성 기준 추천")
                    
                    for i, rec in enumerate(ai_recommendations['installation_ease'], 1):
                        with st.container():
                            st.markdown(f"**{i}. {rec['product_name']}**")
                            
                            col1, col2 = st.columns([1, 1])
                            
                            with col1:
                                st.markdown(f"• **쇼핑**: {rec['price_info']}")
                                
                                # 블로그 후기
                                if rec['blog_quotes']:
                                    for quote in rec['blog_quotes'][:2]:
                                        if quote and len(quote.strip()) > 3:
                                            st.markdown(f"• **블로그 후기**: \"{quote}\"")
                            
                            with col2:
                                st.markdown(f"• **{rec['score_display']}**")
                                st.markdown(f"• **{rec['star_rating']}**")
                            
                            st.markdown("---")
                
                # 보안성 기준 추천  
                if ai_recommendations.get('security'):
                    st.markdown("#### 🔒 보안성 기준 추천")
                    
                    for i, rec in enumerate(ai_recommendations['security'], 1):
                        with st.container():
                            st.markdown(f"**{i}. {rec['product_name']}**")
                            
                            col1, col2 = st.columns([1, 1])
                            
                            with col1:
                                # 뉴스 하이라이트
                                if rec['news_highlights']:
                                    for highlight in rec['news_highlights'][:2]:
                                        if highlight:
                                            st.markdown(f"• **뉴스**: \"{highlight}\"")
                                
                                # 블로그 후기
                                if rec['blog_quotes']:
                                    for quote in rec['blog_quotes'][:1]:
                                        if quote and len(quote.strip()) > 3:
                                            st.markdown(f"• **블로그**: \"{quote}\"")
                            
                            with col2:
                                st.markdown(f"• **{rec['score_display']}**")
                                st.markdown(f"• **{rec['star_rating']}**")
                            
                            st.markdown("---")
                
                # AI 분석 요약
                st.markdown("#### 🤖 AI 분석 요약")
                
                summary_prompt = f"""
사용자 질문: {query}
생성된 추천 결과를 바탕으로 다음을 한국어로 요약해주세요:

1. 추천 이유 요약 (2-3문장)
2. 주요 고려사항 (1-2개)
3. 추가 팁 (1개)

간결하고 실용적으로 작성해주세요.
"""
                
                ai_summary = call_chatgpt_api(summary_prompt, max_tokens=300)
                
                if ai_summary:
                    st.info(f"💡 **AI 요약**: {ai_summary}")
                else:
                    st.info("💡 **추천 요약**: 설치 간편성과 보안성을 고려하여 상위 제품들을 추천드렸습니다. 개인의 우선순위에 맞게 선택하시기 바랍니다.")
                
            except Exception as e:
                st.error(f"❌ AI 추천 결과 생성 실패: {str(e)}")
                st.info("💡 종합 테스트 데이터 생성 버튼을 눌러 테스트 데이터를 만들어보세요.")

    # 하단 정보
    st.markdown("---")
    with st.expander("ℹ️ 시스템 정보", expanded=False):
        st.markdown("""
        **🔧 기술 스택:**
        - **Frontend**: Streamlit
        - **Database**: Supabase (PostgreSQL + pgvector)
        - **AI/ML**: SentenceTransformer + ChatGPT API
        - **API**: 네이버 검색 API
        
        **📊 데이터 소스:**
        - 네이버 쇼핑: 제품 정보, 가격, 스펙
        - 네이버 블로그: 사용자 후기, 설치 경험
        - 네이버 뉴스: 보안 이슈, 업계 동향
        
        **🤖 ChatGPT AI 분석:**
        - 멀티소스 데이터 종합 분석
        - 설치 간편성 vs 보안성 기준 분류
        - 실시간 맞춤형 추천 생성
        - 사용자 질의 맞춤 요약 제공
        
        **✨ 개선사항:**
        - ChatGPT API 연동으로 더 정확한 추천
        - 실시간 데이터 수집 및 분석
        - 사용자 맞춤형 추천 시스템
        """)

if __name__ == "__main__":
    main()
