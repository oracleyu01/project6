"""
네이버 API 데이터 수집 및 통합 텍스트 생성 모듈
제품별로 쇼핑, 블로그, 뉴스 데이터를 수집하여 하나의 텍스트로 통합
"""

import urllib.request
import urllib.parse
import json
import time
import re
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class NaverDataCollector:
    def __init__(self, client_id: str, client_secret: str, supabase_client):
        self.client_id = client_id
        self.client_secret = client_secret
        self.supabase = supabase_client
        
    def collect_product_data(self, product_keyword: str, category_id: int) -> Dict:
        """특정 제품에 대한 멀티소스 데이터 수집"""
        logger.info(f"데이터 수집 시작: {product_keyword}")
        
        # 카테고리별 검색 키워드 가져오기
        category_info = self.get_category_search_keywords(category_id)
        if not category_info:
            logger.error(f"카테고리 정보를 찾을 수 없습니다: {category_id}")
            return {}
        
        # 각 소스별 데이터 수집
        shopping_data = self.collect_shopping_data(product_keyword, category_info['search_keywords'])
        blog_data = self.collect_blog_data(product_keyword, category_info['search_keywords'])
        news_data = self.collect_news_data(product_keyword, category_info['search_keywords'])
        
        # 통합 텍스트 생성
        combined_text = self.create_combined_text(
            product_keyword, shopping_data, blog_data, news_data
        )
        
        # 데이터 품질 평가
        quality_score = self.calculate_data_quality(shopping_data, blog_data, news_data)
        
        result = {
            'product_name': product_keyword,
            'category_id': category_id,
            'combined_text': combined_text,
            'shopping_data': shopping_data,
            'blog_data': blog_data,
            'news_data': news_data,
            'data_quality_score': quality_score,
            'total_source_count': len(shopping_data) + len(blog_data) + len(news_data)
        }
        
        # 데이터베이스에 저장
        saved_id = self.save_raw_data(result)
        result['raw_data_id'] = saved_id
        
        logger.info(f"데이터 수집 완료: {product_keyword}, 총 {result['total_source_count']}개 소스")
        return result
    
    def get_category_search_keywords(self, category_id: int) -> Optional[Dict]:
        """카테고리별 검색 키워드 조회"""
        try:
            result = self.supabase.table('product_categories').select('*').eq('id', category_id).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"카테고리 검색 실패: {e}")
            return None
    
    def collect_shopping_data(self, keyword: str, search_config: Dict) -> List[Dict]:
        """네이버 쇼핑 데이터 수집"""
        shopping_keywords = search_config.get('shopping', [keyword])
        all_items = []
        
        for search_keyword in shopping_keywords:
            items = self.search_naver_api(search_keyword, 'shop', display=50)
            processed_items = []
            
            for item in items:
                try:
                    processed_item = {
                        'title': self.clean_html_tags(item.get('title', '')),
                        'description': self.clean_html_tags(item.get('description', '')),
                        'link': item.get('link', ''),
                        'image': item.get('image', ''),
                        'lprice': int(item.get('lprice', 0)) if item.get('lprice') else 0,
                        'hprice': int(item.get('hprice', 0)) if item.get('hprice') else 0,
                        'brand': item.get('brand', ''),
                        'maker': item.get('maker', ''),
                        'category1': item.get('category1', ''),
                        'category2': item.get('category2', ''),
                        'mallName': item.get('mallName', ''),
                        'productId': item.get('productId', ''),
                        'search_keyword': search_keyword,
                        'collected_at': datetime.now().isoformat()
                    }
                    processed_items.append(processed_item)
                except Exception as e:
                    logger.debug(f"쇼핑 아이템 처리 실패: {e}")
                    continue
            
            all_items.extend(processed_items)
            time.sleep(0.1)  # API 호출 제한
        
        return all_items
    
    def collect_blog_data(self, keyword: str, search_config: Dict) -> List[Dict]:
        """네이버 블로그 데이터 수집"""
        blog_keywords = search_config.get('blog', [f"{keyword} 후기", f"{keyword} 리뷰"])
        all_items = []
        
        for search_keyword in blog_keywords:
            items = self.search_naver_api(search_keyword, 'blog', display=50)
            processed_items = []
            
            for item in items:
                try:
                    processed_item = {
                        'title': self.clean_html_tags(item.get('title', '')),
                        'description': self.clean_html_tags(item.get('description', '')),
                        'link': item.get('link', ''),
                        'bloggername': item.get('bloggername', ''),
                        'bloggerlink': item.get('bloggerlink', ''),
                        'postdate': item.get('postdate', ''),
                        'search_keyword': search_keyword,
                        'collected_at': datetime.now().isoformat()
                    }
                    processed_items.append(processed_item)
                except Exception as e:
                    logger.debug(f"블로그 아이템 처리 실패: {e}")
                    continue
            
            all_items.extend(processed_items)
            time.sleep(0.1)
        
        return all_items
    
    def collect_news_data(self, keyword: str, search_config: Dict) -> List[Dict]:
        """네이버 뉴스 데이터 수집"""
        news_keywords = search_config.get('news', [f"{keyword} 신제품", f"{keyword} 출시"])
        all_items = []
        
        for search_keyword in news_keywords:
            items = self.search_naver_api(search_keyword, 'news', display=30)
            processed_items = []
            
            for item in items:
                try:
                    processed_item = {
                        'title': self.clean_html_tags(item.get('title', '')),
                        'description': self.clean_html_tags(item.get('description', '')),
                        'link': item.get('link', ''),
                        'originallink': item.get('originallink', ''),
                        'pubDate': item.get('pubDate', ''),
                        'search_keyword': search_keyword,
                        'collected_at': datetime.now().isoformat()
                    }
                    processed_items.append(processed_item)
                except Exception as e:
                    logger.debug(f"뉴스 아이템 처리 실패: {e}")
                    continue
            
            all_items.extend(processed_items)
            time.sleep(0.1)
        
        return all_items
    
    def search_naver_api(self, keyword: str, endpoint: str, display: int = 100) -> List[Dict]:
        """네이버 API 검색 (기존 함수 개선)"""
        try:
            encoded_query = urllib.parse.quote(keyword)
            url = f"https://openapi.naver.com/v1/search/{endpoint}?query={encoded_query}&display={display}&sort=sim"
            
            request = urllib.request.Request(url)
            request.add_header("X-Naver-Client-Id", self.client_id)
            request.add_header("X-Naver-Client-Secret", self.client_secret)
            
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    return data.get('items', [])
                else:
                    logger.error(f"네이버 API 오류: {response.getcode()}")
                    return []
                    
        except Exception as e:
            logger.error(f"네이버 API 검색 실패 ({endpoint}): {e}")
            return []
    
    def create_combined_text(self, product_name: str, shopping_data: List, blog_data: List, news_data: List) -> str:
        """모든 수집 데이터를 하나의 텍스트로 통합"""
        sections = []
        
        # 제품명 섹션
        sections.append(f"제품명: {product_name}")
        
        # 쇼핑 정보 섹션
        if shopping_data:
            sections.append("\n=== 쇼핑 정보 ===")
            
            # 가격 정보 정리
            prices = [item['lprice'] for item in shopping_data if item.get('lprice', 0) > 0]
            if prices:
                min_price = min(prices)
                max_price = max(prices)
                avg_price = sum(prices) // len(prices)
                sections.append(f"가격대: 최저 {min_price:,}원 ~ 최고 {max_price:,}원 (평균 {avg_price:,}원)")
            
            # 브랜드 정보
            brands = list(set([item.get('brand', '') for item in shopping_data if item.get('brand')]))
            if brands:
                sections.append(f"주요 브랜드: {', '.join(brands[:5])}")
            
            # 상위 제품 정보
            for i, item in enumerate(shopping_data[:5], 1):
                title = item.get('title', '')
                lprice = item.get('lprice', 0)
                mall = item.get('mallName', '')
                if title and lprice:
                    sections.append(f"{i}. {title} - {lprice:,}원 ({mall})")
        
        # 블로그 후기 섹션  
        if blog_data:
            sections.append("\n=== 사용자 후기 (블로그) ===")
            for i, item in enumerate(blog_data[:10], 1):
                title = item.get('title', '')
                desc = item.get('description', '')
                blogger = item.get('bloggername', '')
                if title and desc:
                    sections.append(f"후기 {i}: {title}")
                    sections.append(f"내용: {desc[:200]}...")
                    if blogger:
                        sections.append(f"작성자: {blogger}")
                    sections.append("")
        
        # 뉴스 섹션
        if news_data:
            sections.append("\n=== 관련 뉴스 ===")
            for i, item in enumerate(news_data[:5], 1):
                title = item.get('title', '')
                desc = item.get('description', '')
                pub_date = item.get('pubDate', '')
                if title and desc:
                    sections.append(f"뉴스 {i}: {title}")
                    sections.append(f"내용: {desc[:150]}...")
                    if pub_date:
                        sections.append(f"발행일: {pub_date}")
                    sections.append("")
        
        combined_text = "\n".join(sections)
        
        # 텍스트 정리 (너무 길면 요약)
        if len(combined_text) > 8000:
            combined_text = combined_text[:8000] + "... (데이터 크기로 인한 자동 절단)"
        
        return combined_text
    
    def calculate_data_quality(self, shopping_data: List, blog_data: List, news_data: List) -> float:
        """수집된 데이터의 품질 점수 계산 (0-1)"""
        score = 0.0
        
        # 데이터 완성도 (각 소스별 데이터 존재 여부)
        if shopping_data:
            score += 0.4
        if blog_data:
            score += 0.4  
        if news_data:
            score += 0.2
        
        # 데이터 양적 품질
        total_items = len(shopping_data) + len(blog_data) + len(news_data)
        if total_items >= 50:
            score += 0.2
        elif total_items >= 20:
            score += 0.1
        
        # 쇼핑 데이터 품질 (가격 정보 완성도)
        if shopping_data:
            price_complete = sum(1 for item in shopping_data if item.get('lprice', 0) > 0)
            price_ratio = price_complete / len(shopping_data)
            score += price_ratio * 0.1
        
        return min(1.0, score)
    
    def save_raw_data(self, data: Dict) -> Optional[int]:
        """원본 데이터 저장"""
        try:
            insert_data = {
                'product_name': data['product_name'],
                'category_id': data['category_id'],
                'search_keyword': data['product_name'],
                'combined_text': data['combined_text'],
                'shopping_data': data['shopping_data'],
                'blog_data': data['blog_data'],
                'news_data': data['news_data'],
                'data_quality_score': data['data_quality_score'],
                'total_source_count': data['total_source_count']
            }
            
            result = self.supabase.table('raw_product_data').insert(insert_data).execute()
            if result.data:
                return result.data[0]['id']
            return None
            
        except Exception as e:
            logger.error(f"원본 데이터 저장 실패: {e}")
            return None
    
    def clean_html_tags(self, text: str) -> str:
        """HTML 태그 제거 및 텍스트 정리"""
        if not text:
            return ""
        
        # HTML 태그 제거
        clean_text = re.sub('<[^<]+?>', '', text)
        
        # 특수 문자 정리
        clean_text = clean_text.replace('&quot;', '"')
        clean_text = clean_text.replace('&amp;', '&')
        clean_text = clean_text.replace('&lt;', '<')
        clean_text = clean_text.replace('&gt;', '>')
        
        # 연속된 공백 정리
        clean_text = re.sub(r'\s+', ' ', clean_text)
        
        return clean_text.strip()

# ========================================
# 사용 예시
# ========================================

def collect_product_data_example():
    """데이터 수집 사용 예시"""
    import os
    from supabase import create_client
    
    # 클라이언트 초기화
    supabase = create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_KEY")
    )
    
    collector = NaverDataCollector(
        client_id=os.environ.get("NAVER_CLIENT_ID"),
        client_secret=os.environ.get("NAVER_CLIENT_SECRET"),
        supabase_client=supabase
    )
    
    # 제품별 데이터 수집
    products = [
        ("삼성 갤럭시북", 2),  # 노트북 카테고리
        ("LG 그램", 2),
        ("맥북 프로", 2),
        ("삼성 도어락", 1),    # 도어락 카테고리
        ("아이폰 15", 3),      # 스마트폰 카테고리
    ]
    
    for product_name, category_id in products:
        try:
            print(f"\n데이터 수집 시작: {product_name}")
            result = collector.collect_product_data(product_name, category_id)
            print(f"수집 완료 - 품질점수: {result['data_quality_score']:.2f}, 소스수: {result['total_source_count']}")
        except Exception as e:
            print(f"수집 실패: {product_name} - {e}")

if __name__ == "__main__":
    collect_product_data_example()
