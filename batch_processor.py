"""
배치 데이터 수집 및 QA 생성 스크립트
여러 제품에 대해 일괄적으로 데이터 수집 및 QA 생성 수행
"""

import os
import sys
import time
import logging
from typing import List, Dict, Tuple
from datetime import datetime

# 환경 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client
from sentence_transformers import SentenceTransformer
import openai

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BatchProcessor:
    def __init__(self):
        """배치 프로세서 초기화"""
        self.supabase = create_client(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_KEY")
        )
        
        openai.api_key = os.environ.get("OPENAI_API_KEY")
        
        # 임베딩 모델 로드
        try:
            self.embedding_model = SentenceTransformer('jhgan/ko-sroberta-multitask')
        except:
            self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        
        logger.info("배치 프로세서 초기화 완료")
    
    def process_product_batch(self, products: List[Tuple[str, int]]) -> Dict:
        """제품 배치 처리"""
        logger.info(f"배치 처리 시작: {len(products)}개 제품")
        
        results = {
            "total_products": len(products),
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        # 데이터 수집기와 QA 생성기 임포트 (실제 사용시 주석 해제)
        # from data_collector import NaverDataCollector
        # from qa_generator import QAGenerator
        
        # collector = NaverDataCollector(
        #     client_id=os.environ.get("NAVER_CLIENT_ID"),
        #     client_secret=os.environ.get("NAVER_CLIENT_SECRET"),
        #     supabase_client=self.supabase
        # )
        
        # qa_generator = QAGenerator(
        #     openai_api_key=os.environ.get("OPENAI_API_KEY"),
        #     supabase_client=self.supabase,
        #     embedding_model=self.embedding_model
        # )
        
        for i, (product_name, category_id) in enumerate(products, 1):
            try:
                logger.info(f"처리 중 ({i}/{len(products)}): {product_name}")
                
                # 1. 데이터 수집
                logger.info(f"  1단계: 데이터 수집 중...")
                # raw_data = collector.collect_product_data(product_name, category_id)
                
                # 시뮬레이션용 (실제 사용시 제거)
                raw_data = self.simulate_data_collection(product_name, category_id)
                
                if not raw_data or raw_data.get('total_source_count', 0) < 5:
                    logger.warning(f"  데이터 수집 실패 또는 데이터 부족: {product_name}")
                    results["failed"] += 1
                    results["details"].append({
                        "product": product_name,
                        "status": "failed",
                        "reason": "데이터 수집 실패"
                    })
                    continue
                
                logger.info(f"  데이터 수집 완료: {raw_data['total_source_count']}개 소스")
                
                # 2. QA 생성
                logger.info(f"  2단계: QA 생성 중...")
                # qa_list = qa_generator.generate_qa_from_raw_data(raw_data['raw_data_id'])
                
                # 시뮬레이션용 (실제 사용시 제거)
                qa_list = self.simulate_qa_generation(raw_data['raw_data_id'])
                
                if not qa_list:
                    logger.warning(f"  QA 생성 실패: {product_name}")
                    results["failed"] += 1
                    results["details"].append({
                        "product": product_name,
                        "status": "failed",
                        "reason": "QA 생성 실패"
                    })
                    continue
                
                logger.info(f"  QA 생성 완료: {len(qa_list)}개")
                
                # 성공 기록
                results["successful"] += 1
                results["details"].append({
                    "product": product_name,
                    "status": "success",
                    "raw_data_id": raw_data.get('raw_data_id'),
                    "qa_count": len(qa_list),
                    "data_quality": raw_data.get('data_quality_score', 0)
                })
                
                # API 호출 제한 고려 (1초 대기)
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"제품 처리 실패: {product_name} - {str(e)}")
                results["failed"] += 1
                results["details"].append({
                    "product": product_name,
                    "status": "error",
                    "reason": str(e)
                })
                continue
        
        logger.info(f"배치 처리 완료: 성공 {results['successful']}개, 실패 {results['failed']}개")
        return results
    
    def simulate_data_collection(self, product_name: str, category_id: int) -> Dict:
        """데이터 수집 시뮬레이션 (개발/테스트용)"""
        logger.info(f"  시뮬레이션: {product_name} 데이터 수집")
        
        # 실제 DB에 시뮬레이션 데이터 저장
        try:
            combined_text = f"""
            제품명: {product_name}
            
            === 쇼핑 정보 ===
            가격대: 200만원~400만원
            주요 브랜드: 삼성, LG, 애플
            1. {product_name} 프리미엄 모델 - 350만원 (공식쇼핑몰)
            2. {product_name} 스탠다드 모델 - 250만원 (온라인몰)
            
            === 사용자 후기 (블로그) ===
            후기 1: 성능이 뛰어나고 사용하기 편리함
            내용: 처음 사용해보는데 예상보다 훨씬 만족스럽습니다. 특히 성능 면에서 기대를 상회했고...
            
            후기 2: 가격 대비 괜찮은 제품
            내용: 다른 제품들과 비교해봤을 때 가성비가 좋은 편입니다. 디자인도 깔끔하고...
            
            === 관련 뉴스 ===
            뉴스 1: {product_name} 신제품 출시로 시장 주목
            내용: 올해 새롭게 출시된 {product_name} 시리즈가 업계의 주목을 받고 있다...
            """
            
            insert_data = {
                'product_name': product_name,
                'category_id': category_id,
                'search_keyword': product_name,
                'combined_text': combined_text,
                'shopping_data': [{"title": f"{product_name} 프리미엄", "lprice": 3500000}],
                'blog_data': [{"title": f"{product_name} 후기", "description": "성능이 뛰어남"}],
                'news_data': [{"title": f"{product_name} 신제품 출시", "description": "시장 주목"}],
                'data_quality_score': 0.8,
                'total_source_count': 15
            }
            
            result = self.supabase.table('raw_product_data').insert(insert_data).execute()
            
            if result.data:
                return {
                    'product_name': product_name,
                    'category_id': category_id,
                    'raw_data_id': result.data[0]['id'],
                    'total_source_count': 15,
                    'data_quality_score': 0.8
                }
            else:
                return {}
                
        except Exception as e:
            logger.error(f"시뮬레이션 데이터 저장 실패: {e}")
            return {}
    
    def simulate_qa_generation(self, raw_data_id: int) -> List[Dict]:
        """QA 생성 시뮬레이션 (개발/테스트용)"""
        logger.info(f"  시뮬레이션: QA 생성 (raw_data_id: {raw_data_id})")
        
        # 원본 데이터 조회
        try:
            raw_result = self.supabase.table('raw_product_data').select('*').eq('id', raw_data_id).execute()
            if not raw_result.data:
                return []
            
            raw_data = raw_result.data[0]
            product_name = raw_data['product_name']
            
            # 시뮬레이션 QA 데이터
            sample_qa = [
                {
                    "question": f"{product_name} 추천해줘",
                    "answer": f"{product_name}은 성능과 디자인이 우수한 제품입니다. 가격대는 200-400만원 수준이며, 사용자 후기도 대체로 긍정적입니다.",
                    "question_type": "recommendation",
                    "confidence": 0.9
                },
                {
                    "question": f"성능 좋은 {product_name.split()[0]} 제품 있나요?",
                    "answer": f"{product_name}의 프리미엄 모델을 추천합니다. 최신 기술이 적용되어 성능이 뛰어나며, 여러 사용자 후기에서도 성능 만족도가 높게 나타납니다.",
                    "question_type": "performance
