# -*- coding: utf-8 -*-
"""
디버그 스크립트: 파일 정보 추출 테스트
사용법: python debug_extract.py "파일경로"
"""

import sys
import re
from pathlib import Path

def debug_month_extraction(text: str):
    """월 추출 디버깅"""
    print("\n" + "="*60)
    print("📅 월 추출 디버깅")
    print("="*60)
    
    # 1순위: 직접 월 표기
    pattern1 = r'(\d{1,2})\s*월'
    matches1 = re.findall(pattern1, text)
    print(f"\n1순위 - '(\\d{{1,2}})\\s*월' 매칭: {matches1}")
    
    # 2순위: 날짜 형식
    pattern2 = r'(\d{1,2})[-/.](\d{1,2})'
    matches2 = re.findall(pattern2, text)
    print(f"2순위 - '(\\d{{1,2}})[-/.](\\d{{1,2}})' 매칭: {matches2}")
    
    # 문제 패턴 확인
    print(f"\n⚠️ '2025-07'에서 잘못 매칭될 수 있는 패턴:")
    test_text = "2025-07-지구과학"
    matches_test = re.findall(r'(\d{1,2})[-/.](\d{1,2})', test_text)
    print(f"   테스트 텍스트: '{test_text}'")
    print(f"   매칭 결과: {matches_test}")
    
def debug_year_extraction(text: str):
    """연도 추출 디버깅"""
    print("\n" + "="*60)
    print("📅 연도 추출 디버깅")
    print("="*60)
    
    # 학년도
    pattern1 = r'(20\d{2})\s*학년도'
    match1 = re.search(pattern1, text)
    print(f"\n'학년도' 패턴 매칭: {match1.group() if match1 else '없음'}")
    
    # 연도+월
    pattern2 = r'(20\d{2})[-./년]\s*([0-1]?\d)[-./월]'
    match2 = re.search(pattern2, text)
    print(f"'연도-월' 패턴 매칭: {match2.groups() if match2 else '없음'}")
    
    # 연도만
    pattern3 = r'(20\d{2})\s*년'
    match3 = re.search(pattern3, text)
    print(f"'연도년' 패턴 매칭: {match3.group() if match3 else '없음'}")

def debug_filename(filepath: str):
    """파일명에서 정보 추출 디버깅"""
    print("\n" + "="*60)
    print("📁 파일명 분석 디버깅")
    print("="*60)
    
    filename = Path(filepath).stem
    print(f"\n파일명: '{filename}'")
    
    # 연도-월 패턴 (YYYY-MM)
    pattern_ym = r'(20\d{2})[-./](\d{1,2})'
    match_ym = re.search(pattern_ym, filename)
    if match_ym:
        print(f"✅ 연도-월 패턴 매칭: 연도={match_ym.group(1)}, 월={match_ym.group(2)}")
    else:
        print("❌ 연도-월 패턴 매칭 실패")
    
    # 현재 문제가 되는 패턴
    bad_pattern = r'(\d{1,2})[-/.](\d{1,2})'
    matches_bad = re.findall(bad_pattern, filename)
    print(f"\n⚠️ 문제 패턴 매칭: {matches_bad}")
    if matches_bad:
        print(f"   첫 번째 매칭이 {matches_bad[0][0]}으로 시작 - 이것이 월로 잘못 인식될 수 있음!")

def test_correct_pattern(filename: str):
    """올바른 패턴 테스트"""
    print("\n" + "="*60)
    print("🔧 올바른 패턴 제안")
    print("="*60)
    
    # 파일명에서 YYYY-MM 또는 YYYY_MM 추출
    # 연도가 먼저 오는 경우를 정확히 매칭
    correct_pattern = r'(20\d{2})[-_./](\d{1,2})'
    match = re.search(correct_pattern, filename)
    if match:
        year = match.group(1)
        month = int(match.group(2))
        print(f"✅ 올바른 추출: 연도={year}, 월={month:02d}")
    else:
        print("❌ 매칭 실패")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"\n🔍 파일 분석: {filepath}")
        debug_filename(filepath)
        test_correct_pattern(Path(filepath).stem)
    else:
        # 기본 테스트
        test_files = [
            "2025-07-지구과학.hwp",
            "2025-03-지구과학.hwp",
            "2025-05-지구과학.hwp",
            "2025-10-지구과학.pdf",
            "2025학년도-06-수학.hwp",
        ]
        
        for filename in test_files:
            print("\n" + "="*60)
            print(f"📄 테스트: {filename}")
            debug_filename(filename)
            test_correct_pattern(filename)
