# -*- coding: utf-8 -*-
"""
디버그 스크립트 - PDF에서 추출된 텍스트와 정규표현식 매칭 테스트
"""
import re
import sys
from pdfminer.high_level import extract_text as pdf_extract_text

# config.py의 패턴들
YEAR_PATTERNS = [
    r'(20[0-9]{2})[\s\n\r]*학[\s\n\r]*년[\s\n\r]*도',
    r'(20[0-9]{2}학년도)',
    r'(20[0-9]{2})년',
    r'(20[0-9]{2})\s*[\.\/\-]',
    r'[\'`](20[0-9]{2})',
    r'(20[0-9]{2})',
]

SUNEUNG_PATTERNS = [
    r'대[\s\n\r]*학[\s\n\r]*수[\s\n\r]*학[\s\n\r]*능[\s\n\r]*력[\s\n\r]*시[\s\n\r]*험',
    r'수[\s\n\r]*학[\s\n\r]*능[\s\n\r]*력[\s\n\r]*시[\s\n\r]*험',
    r'능[\s\n\r]*력[\s\n\r]*시[\s\n\r]*험',
]

SUNEUNG_KEYWORDS = ['대학수학능력시험', '대학수학능력', '수학능력시험', '수능', 'CSAT', '능력시험']

def test_pdf(filepath):
    print("=" * 60)
    print(f"PDF 분석: {filepath}")
    print("=" * 60)
    
    # PDF에서 텍스트 추출
    try:
        text = pdf_extract_text(filepath, maxpages=1)
    except Exception as e:
        print(f"[오류] PDF 읽기 실패: {e}")
        return
    
    if not text:
        print("[오류] 텍스트가 추출되지 않았습니다.")
        return
    
    # 추출된 텍스트 출력 (처음 2000자)
    print("\n[1] 추출된 원본 텍스트 (처음 2000자):")
    print("-" * 40)
    print(repr(text[:2000]))  # repr로 출력하여 특수문자 확인
    print("-" * 40)
    
    # 읽기 쉬운 형태로도 출력
    print("\n[2] 추출된 텍스트 (읽기 쉽게):")
    print("-" * 40)
    print(text[:2000])
    print("-" * 40)
    
    # 연도 패턴 테스트
    print("\n[3] 연도 패턴 매칭 테스트:")
    for i, pattern in enumerate(YEAR_PATTERNS):
        match = re.search(pattern, text)
        if match:
            print(f"  패턴 {i}: {pattern}")
            print(f"    → 매칭: '{match.group(0)}'")
            print(f"    → 캡처: '{match.group(1)}'")
            break
        else:
            print(f"  패턴 {i}: 매칭 안됨")
    
    # 수능 패턴 테스트
    print("\n[4] 수능 정규표현식 패턴 테스트:")
    for i, pattern in enumerate(SUNEUNG_PATTERNS):
        match = re.search(pattern, text)
        if match:
            print(f"  패턴 {i}: 매칭됨 → '{match.group(0)}'")
            break
        else:
            print(f"  패턴 {i}: 매칭 안됨")
    
    # 수능 키워드 테스트
    print("\n[5] 수능 키워드 직접 검색:")
    for keyword in SUNEUNG_KEYWORDS:
        if keyword in text:
            print(f"  '{keyword}': 발견됨!")
        else:
            print(f"  '{keyword}': 없음")
    
    # "2026" 직접 검색
    print("\n[6] '2026' 직접 검색:")
    if "2026" in text:
        idx = text.index("2026")
        print(f"  발견! 위치: {idx}")
        print(f"  주변 텍스트: '{text[max(0,idx-10):idx+30]}'")
    else:
        print("  '2026' 없음")
    
    # "학년도" 직접 검색
    print("\n[7] '학년도' 직접 검색:")
    if "학년도" in text:
        idx = text.index("학년도")
        print(f"  발견! 위치: {idx}")
        print(f"  주변 텍스트: '{text[max(0,idx-10):idx+20]}'")
    else:
        print("  '학년도' 없음")
    
    # "대학수학능력시험" 직접 검색
    print("\n[8] '수학능력' 직접 검색:")
    if "수학능력" in text:
        idx = text.index("수학능력")
        print(f"  발견! 위치: {idx}")
        print(f"  주변 텍스트: '{text[max(0,idx-10):idx+30]}'")
    else:
        print("  '수학능력' 없음")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python debug_pdf.py <PDF파일경로>")
        print("예: python debug_pdf.py test.pdf")
    else:
        test_pdf(sys.argv[1])
