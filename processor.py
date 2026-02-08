# -*- coding: utf-8 -*-
"""
Smart File Renamer - Processor Module
파일 분석 및 이름 변경 로직
Version: 1.0.0
"""

import re
import json
import shutil
import zlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

from pdfminer.high_level import extract_text as pdf_extract_text

try:
    import olefile
    HAS_OLEFILE = True
except ImportError:
    HAS_OLEFILE = False

# pyhwp - HWP 전용 파서
try:
    from hwp5.hwp5txt import extract_text as hwp_extract_text
    from hwp5.xmlmodel import Hwp5File
    HAS_PYHWP = True
except ImportError:
    HAS_PYHWP = False

from config import (
    SUBJECT_KEYWORDS, SUBJECT_SUBCATEGORIES, SUBJECT_CATEGORIES, DOCUMENT_KEYWORDS,
    YEAR_PATTERNS, MONTH_PATTERNS, SUPPORTED_EXTENSIONS, FileStatus,
    SUNEUNG_KEYWORDS, SUNEUNG_PATTERNS, MOCK_EXAM_MONTH_MAP
)


@dataclass
class ExtractedInfo:
    """추출된 파일 정보"""
    year: str = ""
    month: str = ""
    subject: str = ""
    subject_main: str = ""
    subject_sub: str = ""
    grade: str = ""  # 학년 (고1, 고2, 고3, 중1 등)
    confidence: float = 0.0
    source: str = ""
    raw_text: str = ""
    header_text: str = ""
    is_smart_extracted: bool = False  # 스마트 추출 여부
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileEntry:
    """파일 항목 데이터"""
    original_path: str
    original_name: str
    extension: str
    extracted_info: ExtractedInfo = field(default_factory=ExtractedInfo)
    proposed_name: str = ""
    status: str = FileStatus.READY
    error_message: str = ""
    order: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RenameTransaction:
    """이름 변경 트랜잭션"""
    timestamp: str
    operations: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


class FileProcessor:
    """파일 처리 및 분석 클래스"""
    
    # 텍스트 추출 설정 (확장됨)
    HEADER_MAX_LINES = 40       # 상단 40줄 (20→40)
    HEADER_MAX_CHARS = 1500     # 상단 1500자 (500→1500)
    RAW_TEXT_MAX_CHARS = 3000   # 전체 3000자 (2000→3000)
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.current_transaction: Optional[RenameTransaction] = None
        self.custom_keywords: List[str] = []
        
    def set_custom_keywords(self, keywords: List[str]):
        """사용자 정의 키워드 설정"""
        self.custom_keywords = keywords
        
    def is_supported_file(self, filepath: str) -> bool:
        """지원되는 파일 확장자인지 확인"""
        return Path(filepath).suffix.lower() in SUPPORTED_EXTENSIONS
    
    def scan_folder(self, folder_path: str) -> List[FileEntry]:
        """폴더 스캔"""
        entries = []
        folder = Path(folder_path)
        
        if not folder.exists():
            return entries
            
        for filepath in folder.iterdir():
            if filepath.is_file() and self.is_supported_file(str(filepath)):
                entries.append(FileEntry(
                    original_path=str(filepath),
                    original_name=filepath.stem,
                    extension=filepath.suffix.lower()
                ))
                
        return entries
    
    def scan_files(self, file_paths: List[str]) -> List[FileEntry]:
        """파일 목록에서 항목 생성"""
        entries = []
        
        for filepath in file_paths:
            path = Path(filepath)
            if path.is_file() and self.is_supported_file(filepath):
                entries.append(FileEntry(
                    original_path=filepath,
                    original_name=path.stem,
                    extension=path.suffix.lower()
                ))
            elif path.is_dir():
                entries.extend(self.scan_folder(filepath))
                
        return entries
    
    def analyze_file(self, entry: FileEntry) -> FileEntry:
        """파일 분석"""
        try:
            ext = entry.extension.lower()
            
            if ext == '.pdf':
                entry.extracted_info = self._analyze_pdf(entry.original_path)
            elif ext in ['.hwp', '.hwpx']:
                entry.extracted_info = self._analyze_hwp(entry.original_path)
                # DEBUG: HWP 분석 직후 결과 출력
                print(f"[DEBUG] HWP 분석 직후:")
                print(f"  연도: {entry.extracted_info.year}")
                print(f"  월: {entry.extracted_info.month}")
                print(f"  분류: {entry.extracted_info.subject}")
                print(f"  학년: {entry.extracted_info.grade}")
                print(f"  소스: {entry.extracted_info.source}")
            
            # 파일명에서 추가 정보 추출
            filename_info = self._extract_from_filename(entry.original_path)
            # DEBUG: 파일명 추출 결과
            print(f"[DEBUG] 파일명 추출 결과:")
            print(f"  연도: {filename_info.year}")
            print(f"  월: {filename_info.month}")
            print(f"  분류: {filename_info.subject}")
            print(f"  학년: {filename_info.grade}")
            
            entry.extracted_info = self._merge_info(entry.extracted_info, filename_info)
            # DEBUG: 병합 후 결과
            print(f"[DEBUG] 병합 후:")
            print(f"  연도: {entry.extracted_info.year}")
            print(f"  월: {entry.extracted_info.month}")
            print(f"  분류: {entry.extracted_info.subject}")
            print(f"  학년: {entry.extracted_info.grade}")
            
            # 신뢰도에 따른 상태 설정
            entry.status = FileStatus.READY if entry.extracted_info.confidence >= 0.5 else FileStatus.NEEDS_CHECK
                
        except Exception as e:
            entry.status = FileStatus.ERROR
            entry.error_message = str(e)
            entry.extracted_info = ExtractedInfo()
            
        return entry
    
    def _extract_header_text(self, text: str) -> str:
        """상단 텍스트 추출"""
        if not text:
            return ""
            
        lines = text.strip().split('\n')
        header_lines = []
        char_count = 0
        
        for line in lines[:self.HEADER_MAX_LINES]:
            line = line.strip()
            if line and char_count < self.HEADER_MAX_CHARS:
                header_lines.append(line)
                char_count += len(line)
                
        return '\n'.join(header_lines)
    
    # =========================================================================
    # 통합 메타데이터 추출 함수 (PDF, HWP, HWPX 공통)
    # =========================================================================
    
    def _extract_metadata(self, text: str, info: ExtractedInfo) -> ExtractedInfo:
        """
        문서 텍스트에서 메타데이터 추출 (통합 로직)
        - 헤더 영역 (상위 20줄) 집중 분석
        - 날짜 추출: 완전한 날짜 > 학년도 > 연도 단독 > 분기/반기
        - 분류 추출: 사용자 키워드 > 과목 키워드 > 접미사 추론
        """
        confidence = 0.0
        
        # ===== 1. 헤더 영역 정의 =====
        lines = text.strip().split('\n')
        header_lines = [line.strip() for line in lines[:self.HEADER_MAX_LINES] if line.strip()]
        header_text = '\n'.join(header_lines)
        
        # 노이즈 제거
        header_text_clean = self._clean_header_text(header_text)
        
        info.header_text = header_text
        info.raw_text = text[:self.RAW_TEXT_MAX_CHARS]
        
        # ===== 2. 날짜 추출 (우선순위 기반) =====
        info, date_confidence = self._extract_date_priority(header_lines, header_text_clean, info)
        confidence += date_confidence
        
        # ===== 3. 분류 추출 =====
        info, cat_confidence = self._extract_category(header_lines, header_text_clean, info)
        confidence += cat_confidence
        
        # ===== 4. 제목 추출 =====
        if not info.subject:
            info = self._extract_title_heuristic(header_lines, info)
        
        info.confidence = min(confidence, 1.0)
        return info
    
    def _clean_header_text(self, text: str) -> str:
        """헤더 텍스트 노이즈 제거"""
        # 무의미한 패턴 제거
        noise_patterns = [
            r'\[PAGE\]', r'e-mail\s*:', r'Tel\s*:', r'Fax\s*:',
            r'-\s*\d+\s*-',  # 쪽번호 (- 1 -)
            r'^\d+$',  # 숫자만 있는 줄
        ]
        result = text
        for pattern in noise_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        # 과도한 공백 정리
        result = re.sub(r'\s+', ' ', result)
        return result.strip()
    
    def _extract_date_priority(self, header_lines: List[str], header_text: str, info: ExtractedInfo) -> Tuple[ExtractedInfo, float]:
        """
        날짜 추출 (우선순위 기반) - 개선된 버전
        
        핵심: 시험/평가 관련 월 우선, 편집일자(YYYY년 MM월 DD일) 제외
        """
        confidence = 0.0
        found_date = False
        
        # ----- 1순위: 시험/평가 관련 월 우선 추출 -----
        exam_month_patterns = [
            r'(\d{1,2})\s*월\s*(?:고\d|중\d)',           # N월 고3
            r'(\d{1,2})\s*월\s*(?:전국연합|모의|학력)',   # N월 전국연합
            r'(\d{1,2})\s*월\s*(?:평가|고사|시험)',       # N월 평가
            r'(?:고\d|중\d)\s*(\d{1,2})\s*월',           # 고3 N월
        ]
        
        for pattern in exam_month_patterns:
            match = re.search(pattern, header_text)
            if match:
                month = int(match.group(1))
                if 1 <= month <= 12:
                    info.month = f"{month:02d}"
                    # 연도도 함께 추출 (학년도 우선)
                    year_match = re.search(r'(20\d{2})\s*학년도', header_text)
                    if year_match:
                        info.year = year_match.group(1) + "학년도"
                    else:
                        year_match = re.search(r'(20\d{2})\s*년', header_text)
                        if year_match:
                            info.year = year_match.group(1)
                    confidence = 0.45
                    found_date = True
                    break
        
        # ----- 2순위: 학년도 (1순위 실패 시) -----
        if not found_date:
            haknundo_match = re.search(r'(20\d{2})\s*학년도', header_text)
            if haknundo_match:
                info.year = haknundo_match.group(1) + "학년도"
                confidence = 0.4
                found_date = True
                
                # 학년도와 함께 월 검색
                month_match = re.search(r'(\d{1,2})\s*월', header_text)
                if month_match:
                    month = int(month_match.group(1))
                    if 1 <= month <= 12:
                        info.month = f"{month:02d}"
                        confidence += 0.1

        # ----- 3순위: 연도+월 (1, 2순위 실패 시) -----
        if not found_date:
            ym_match = re.search(r'(20\d{2})\s*년\s*(\d{1,2})\s*월(?!\s*\d{1,2}\s*일)', header_text)
            if ym_match:
                info.year = ym_match.group(1)
                month = int(ym_match.group(2))
                if 1 <= month <= 12:
                    info.month = f"{month:02d}"
                confidence = 0.35
                found_date = True

        # ----- 4순위: 연도 단독 (1~3순위 실패 시) -----
        if not found_date and not info.year:
            year_patterns = [
                r'제\s*(20\d{2})\s*-\s*\d+\s*호',  # 제 2024 - 1 호
                r'(20\d{2})\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}', # 2024.03.01
                r'(20\d{2})',  # 2024 (최후의 수단)
            ]
            for pattern in year_patterns:
                match = re.search(pattern, header_text)
                if match:
                    # 학년과 혼동 방지
                    start_pos = match.start()
                    upcoming_text = header_text[match.end():match.end()+10]
                    if "학년" in upcoming_text:
                        continue
                        
                    info.year = match.group(1)
                    confidence = 0.2
                    break
        
        # ===== 월 추출 세분화 (연도 찾은 경우) =====
        if info.year and not info.month:
            info.month = self._extract_month_detail(header_text)
            if info.month:
                confidence += 0.1
        
        # ===== 학년 추출 =====
        if not info.grade:
            grade_patterns = [
                r'(고)\s*([1-3])(?!\d)',           # 고3
                r'(중)\s*([1-3])(?!\d)',           # 중3
                r'(고등학교)\s*([1-3])\s*학년',
                r'(중학교)\s*([1-3])\s*학년',
                r'(초등학교)\s*([1-6])\s*학년',
                r'(고등)\s*([1-3])\s*학년',
                r'(중등)\s*([1-3])\s*학년',
            ]
            
            for pattern in grade_patterns:
                match = re.search(pattern, header_text)
                if match:
                    prefix_full = match.group(1)
                    num = match.group(2)
                    
                    if prefix_full in ['고', '고등학교', '고등']:
                        prefix = '고'
                    elif prefix_full in ['중', '중학교', '중등']:
                        prefix = '중'
                    elif prefix_full == '초등학교':
                        prefix = '초'
                    else:
                        prefix = prefix_full[0]
                    
                    info.grade = f"{prefix}{num}"
                    print(f"[DEBUG] 학년 추출 성공: {info.grade} (패턴: {pattern})")
                    break
        
        # ===== 최후의 수단: 공백 제거 후 재시도 =====
        header_text_nospace = re.sub(r'\s+', '', header_text)
        
        # 1. 연도 재시도
        if not info.year:
            year_match = re.search(r'(20\d{2})학년도', header_text_nospace)
            if year_match:
                info.year = year_match.group(1) + "학년도"
                confidence += 0.2
        
        # 2. 월 재시도
        if not info.month:
            month_match = re.search(r'(\d{1,2})월(?:고|중|전국|학력|모의)', header_text_nospace)
            if month_match:
                month = int(month_match.group(1))
                if 1 <= month <= 12:
                    info.month = f"{month:02d}"
                    confidence += 0.2
            
        # 3. 학년 재시도
        if not info.grade:
            grade_match = re.search(r'(고|중)([1-3])', header_text_nospace)
            if grade_match:
                 prefix = grade_match.group(1)
                 num = grade_match.group(2)
                 info.grade = f"{prefix}{num}"
                 print(f"[DEBUG] 공백 제거 후 학년 추출: {info.grade}")

        return info, confidence
    
    def _extract_month_detail(self, text: str) -> str:
        """
        월 추출 세분화 (우선순위 기반) - 개선된 버전
        
        핵심: 시험/평가 관련 월을 우선 추출, 편집일자는 제외
        
        1순위: 시험/평가 키워드와 함께 있는 월 (7월 모의평가, 3월 학력평가)
        2순위: 수능 키워드
        3순위: 일반 월 표기 (단, 편집일자 형태 제외)
        4순위: 분기/반기 매핑
        """
        
        # ----- 1순위: 시험/평가 관련 월 우선 추출 -----
        # "N월 고N", "N월 모의", "N월 학력", "N월 전국연합" 등의 패턴
        exam_month_patterns = [
            r'(\d{1,2})\s*월\s*(?:고\d|중\d)',           # N월 고3, N월 중2
            r'(\d{1,2})\s*월\s*(?:전국연합|모의|학력)',   # N월 전국연합, N월 모의
            r'(\d{1,2})\s*월\s*(?:평가|고사|시험)',       # N월 평가, N월 고사
            r'(?:고\d|중\d)\s*(\d{1,2})\s*월',           # 고3 N월
        ]
        
        for pattern in exam_month_patterns:
            match = re.search(pattern, text)
            if match:
                month = int(match.group(1))
                if 1 <= month <= 12:
                    return f"{month:02d}"
        
        # ----- 2순위: 연도와 함께 있지만 일(日)이 없는 월 -----
        # "2025년 7월" O, "2025년 5월 10일" X (편집일자)
        year_month_patterns = [
            r'20\d{2}\s*년\s*(\d{1,2})\s*월\s*(?:고|전국|모의|학력|평가)',  # 2025년 7월 고3...
            r'20\d{2}\s*년\s*(\d{1,2})\s*월\s*(?![0-3]?\d\s*일)',           # 2025년 7월 (뒤에 "일"이 없음)
        ]
        
        for pattern in year_month_patterns:
            match = re.search(pattern, text)
            if match:
                month = int(match.group(1))
                if 1 <= month <= 12:
                    return f"{month:02d}"
        
        # ----- 3순위: 수능/대수능 키워드 → 11월 -----
        suneung_keywords = [
            '대학수학능력시험', '수학능력시험', '능력시험', '수능',
            '대수능', 'CSAT', '수능특강', '수능완성',
        ]
        for kw in suneung_keywords:
            if kw in text:
                return "11"
        
        # ----- 4순위: 모의평가/학력평가 월 추론 -----
        # "6월 모의평가", "9월 모의고사" 등
        mock_patterns = [
            (r'(\d{1,2})\s*월\s*모의', None),      # N월 모의...
            (r'(\d{1,2})\s*월\s*학력', None),      # N월 학력...
            (r'모의\s*(\d{1,2})\s*월', None),      # 모의 N월
        ]
        
        for pattern, _ in mock_patterns:
            match = re.search(pattern, text)
            if match:
                month = int(match.group(1))
                if 1 <= month <= 12:
                    return f"{month:02d}"
        
        # 특정 모의평가 명칭 → 월 추론
        mock_exam_month_map = {
            '3월 학력평가': '03', '3월 모의고사': '03',
            '4월 학력평가': '04', '4월 모의고사': '04',
            '6월 모의평가': '06', '6월 모의고사': '06',
            '7월 학력평가': '07', '7월 모의고사': '07',
            '9월 모의평가': '09', '9월 모의고사': '09',
            '10월 학력평가': '10', '10월 모의고사': '10',
            '11월 모의평가': '11',
        }
        
        for exam_name, month_val in mock_exam_month_map.items():
            if exam_name in text:
                return month_val
        
        # ----- 4순위: 분기/반기 매핑 -----
        half_year_map = {
            '상반기': '06', '하반기': '12',
            '1분기': '03', '2분기': '06', '3분기': '09', '4분기': '12',
            '1/4분기': '03', '2/4분기': '06', '3/4분기': '09', '4/4분기': '12',
        }
        for term, month_val in half_year_map.items():
            if term in text:
                return month_val
        
        # ----- 5순위: 학기 → 월 추론 -----
        semester_map = {
            '1학기': '03', '2학기': '09',
            '1학기중간': '04', '1학기기말': '06',
            '2학기중간': '10', '2학기기말': '12',
            '중간고사': None,  # 학기 정보 필요
            '기말고사': None,
        }
        
        if '1학기' in text:
            if '중간' in text:
                return '04'
            elif '기말' in text:
                return '06'
            return '03'
        if '2학기' in text:
            if '중간' in text:
                return '10'
            elif '기말' in text:
                return '12'
            return '09'
        
        return ""
    
    def _extract_category(self, header_lines: List[str], header_text: str, info: ExtractedInfo) -> Tuple[ExtractedInfo, float]:
        """
        분류 추출 (종합 판단 버전)
        
        모든 가능성을 스캔한 후 최적의 조합을 사용합니다.
        1. 괄호/꺽쇠 안의 내용 (최우선)
        2. 수능 교시 정보 (매우 강력)
        3. 사용자 키워드
        4. 과목명 + 문서유형
        5. 단일 과목명 또는 문서유형
        """
        confidence = 0.0
        
        found_bracket = ""
        found_custom = ""
        found_subject = ""
        found_doc_type = ""
        found_period_subject = ""
        
        # [전처리] 과목 오탐지를 유발하는 시험 명칭 제거
        # "대학수학능력시험", "전국연합학력평가" 등에서 "수학", "과학" 등이 잘못 추출되는 것 방지
        # 공백이 섞여 있을 수도 있으므로 \s* 사용
        noise_patterns = [
            r'대학\s*수학\s*능력\s*시험',
            r'수학\s*능력\s*시험',
            r'수학\s*능력\s*평가',
            r'과학\s*기술', r'사회\s*과학', r'자연\s*과학',
            r'한국\s*교육\s*과정', r'교육\s*과정\s*평가\s*원'
        ]
        
        header_text_clean = header_text
        for pattern in noise_patterns:
            header_text_clean = re.sub(pattern, ' ', header_text_clean)
            
        # ----- 1. 괄호/꺽쇠 안의 내용 추출 (0순위) -----
        bracket_patterns = [
            r'영역\s*\(([가-힣]+(?:\s*[IⅠⅡ1-2]+)?)\)',       # 과학탐구 영역(물리학 I)
            r'\(([가-힣]+\s*[IⅠⅡ1-2]+)\)',                   # (물리학 I)
            r'<([가-힣a-zA-Z0-9]+(?:탐구|영역)?)>\s*영역',   # <과학탐구> 영역
            r'<([가-힣a-zA-Z0-9]+)>',                        # <과학탐구>
            r'\[([가-힣a-zA-Z0-9\s]+)\]',                    # [국어]
            r'【([가-힣a-zA-Z0-9\s]+)】',                    # 【수학】
        ]
        
        # 괄호 제외 패턴
        exclude_bracket_patterns = [
            r'^\d+점$', r'^\d+번$', r'^\d+$', r'^제\d+', r'^총\d+', r'^각\d+',
            r'^page', r'^\d+페이지$', r'^[A-Z]$', r'^[a-z]$', r'^[1-9]~[1-9]$'
        ]
        
        for pattern in bracket_patterns:
            match = re.search(pattern, header_text)
            if match:
                found = match.group(1).strip()
                if 2 <= len(found) <= 15:
                    is_excluded = False
                    for excl in exclude_bracket_patterns:
                        if re.search(excl, found, re.IGNORECASE):
                            is_excluded = True
                            break
                    if not is_excluded:
                        found_bracket = found
                        break
        
        # ----- 2. 수능 교시 추론 (0.5순위 - 매우 강력) -----
        # "대학수학능력시험"은 전처리에서 제거되었을 수 있으므로 원본 header_text 사용
        if '교시' in header_text:
             period_match = re.search(r'제\s*([1-4])\s*교시', header_text)
             # 또는 "1교시", "2교시"
             if not period_match:
                 period_match = re.search(r'([1-4])\s*교시', header_text)
                 
             if period_match:
                period_num = period_match.group(1)
                exam_period_map = {
                    '1': '국어',
                    '2': '수학', 
                    '3': '영어',
                    # 4교시는 한국사/탐구이므로 특정 과목으로 확정하진 않음 (탐구 과목명 추출 우선)
                }
                if period_num in exam_period_map:
                    found_period_subject = exam_period_map[period_num]
        
        # ----- 3. 사용자 정의 키워드 (1순위) -----
        for keyword in self.custom_keywords:
            if keyword in header_text_clean:  # [수정] 전처리된 텍스트 사용
                found_custom = keyword
                for line in header_lines:
                    if keyword in line:
                        expanded = self._extract_compound_noun(line, keyword)
                        if expanded:
                            found_custom = expanded
                        break
                break

        # ----- 4. 과목 키워드 (세분류 > 대분류) -----
        # 전처리된 텍스트(header_text_clean) 사용 -> 대학수학능력시험 등 제외됨
        
        # 세분류 (물리1, 생명과학2 등)
        for keyword in SUBJECT_SUBCATEGORIES:
            if keyword in header_text_clean:
                found_subject = keyword
                info.subject_sub = keyword
                break
        
        # 대분류 (국어, 수학 등) - 세분류가 없을 때만
        if not found_subject:
            for keyword in SUBJECT_CATEGORIES:
                if keyword in header_text_clean:
                    found_subject = keyword
                    info.subject_main = keyword
                    break
                        
        # ----- 5. 문서 유형 키워드 (세특, 생기부 등) -----
        target_doc_keywords = DOCUMENT_KEYWORDS
        for keyword in target_doc_keywords:
            if keyword in header_text: # 문서 유형은 원본에서 찾아도 됨 (큰 문제 없음)
                found_doc_type = keyword
                break

        # ===== 최종 조합 및 결정 =====
        
        # 1. 교시 정보와 괄호 정보가 충돌하는 경우
        # 보통 괄호 정보(예: (지구과학I))가 교시(4교시)보다 구체적이므로 괄호 우선
        
        # 0순위: 괄호 내용
        if found_bracket:
            info.subject = found_bracket
            confidence = 0.6
            return info, confidence
            
        # 0.5순위: 사용자 키워드
        if found_custom:
            info.subject = found_custom
            confidence = 0.7
            return info, confidence
            
        # 0.8순위: 수능 교시 정보 (1~3교시는 과목이 고정적이므로 과목 키워드보다 신뢰)
        if found_period_subject:
            # 단, 4교시(탐구)는 제외했으므로 국/수/영에 한함
            # 만약 found_subject가 다른 과목(예: 과학)이고 교시는 1교시(국어)라면 -> 국어 우선
            info.subject = found_period_subject
            # 문서유형이 있으면 붙여줌 (예: 국어 시험지)
            if found_doc_type and found_doc_type not in ['문제지', '시험지', '정답']:
                 info.subject += f" {found_doc_type}"
            confidence = 0.65
            return info, confidence

        # 1순위: 과목 + 문서유형 조합 (예: 국어 세특)
        if found_subject and found_doc_type:
            if found_doc_type in ['문제지', '시험지', '평가문제', '정답']:
                info.subject = found_subject
            else:
                info.subject = f"{found_subject} {found_doc_type}"
            confidence = 0.6
            return info, confidence
            
        # 2순위: 문서 유형 단독
        if found_doc_type:
            info.subject = found_doc_type
            confidence = 0.4
            return info, confidence
            
        # 3순위: 과목 단독
        if found_subject:
            info.subject = found_subject
            confidence = 0.35
            return info, confidence
            
        # 4순위: 접미사 기반 추론
        suffix_patterns = [
            (r'(\S{2,8}서)(?:\s|$|[,.])', '문서'),     # ~서
            (r'(\S{2,8}록)(?:\s|$|[,.])', '기록'),     # ~록
            (r'(\S{2,8}안)(?:\s|$|[,.])', '기획'),     # ~안
            (r'(\S{2,8}지)(?:\s|$|[,.])', '시험'),     # ~지
            (r'(\S{2,8}문)(?:\s|$|[,.])', '공문'),     # ~문
            (r'(\S{2,8}표)(?:\s|$|[,.])', '양식'),     # ~표
            (r'(\S{2,8}부)(?:\s|$|[,.])', '기록'),     # ~부
        ]
        
        suffix_stopwords = {'수', '등', '및', '중', '후', '내', '외', '더', '덜'}
        
        for line in header_lines[:7]:
            for pattern, category_hint in suffix_patterns:
                match = re.search(pattern, line)
                if match:
                    found_word = match.group(1)
                    if (len(found_word) >= 2 and 
                        found_word not in suffix_stopwords and
                        not found_word.isdigit()):
                        info.subject = found_word
                        confidence = 0.2
                        return info, confidence
        
        return info, confidence
    
    def _extract_compound_noun(self, line: str, keyword: str) -> str:
        """복합 명사 확장 (예: '주간 개발팀 회의록' 추출)"""
        # 키워드 앞의 수식어 2개까지 포함
        pattern = r'((?:\S+\s+){0,2})' + re.escape(keyword)
        match = re.search(pattern, line)
        if match:
            prefix = match.group(1).strip()
            if prefix:
                return prefix + " " + keyword
        return keyword
    
    def _extract_title_heuristic(self, header_lines: List[str], info: ExtractedInfo) -> ExtractedInfo:
        """제목 추출 (휴리스틱 점수 기반)"""
        # 배제 패턴
        exclude_patterns = [
            r'^20\d{2}[-./]',  # 날짜만 있는 줄
            r'^[0-9]+$',       # 숫자만
            r'^(대외비|Confidential|비공개)$',  # 보안 등급
            r'^제\s*\d+\s*교시$',  # 교시
            r'^(홀수|짝수)형$',    # 시험 형태
        ]
        
        best_score = 0
        best_line = ""
        
        for i, line in enumerate(header_lines[:7]):
            if len(line) < 4 or len(line) > 60:
                continue
            
            # 배제 조건 체크
            excluded = False
            for pattern in exclude_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    excluded = True
                    break
            if excluded:
                continue
            
            # 점수 산정
            score = 0
            
            # 위치 점수 (상단일수록 높음)
            score += max(0, 20 - i * 3)
            
            # 길이 점수 (적당한 길이)
            if 10 <= len(line) <= 40:
                score += 15
            
            # 한글/영문만 (특수문자 적음)
            special_count = len(re.findall(r'[^\w\s가-힣]', line))
            if special_count <= 2:
                score += 10
            
            # 키워드 포함 시 가산점
            if any(kw in line for kw in SUBJECT_SUBCATEGORIES):
                score += 25
            if any(kw in line for kw in SUBJECT_CATEGORIES):
                score += 20
            
            if score > best_score:
                best_score = score
                best_line = line
        
        if best_line and not info.subject:
            # 제목에서 분류 키워드 추출 시도
            for kw in SUBJECT_SUBCATEGORIES:
                if kw in best_line:
                    info.subject = kw
                    break
            if not info.subject:
                for kw in SUBJECT_CATEGORIES:
                    if kw in best_line:
                        info.subject = kw
                        break
        
        return info
    
    # =========================================================================
    # 파일 형식별 분석 함수 (모두 _extract_metadata 호출)
    # =========================================================================
    
    def _analyze_pdf(self, filepath: str) -> ExtractedInfo:
        """PDF 파일 분석"""
        info = ExtractedInfo(source="content")
        
        try:
            text = pdf_extract_text(filepath, maxpages=1)
            if text:
                print(f"[DEBUG] PDF 원본 텍스트 (초반 300자):\n{text[:300]}")
                print("-" * 50)
                info = self._extract_metadata(text, info)
                # DEBUG: PDF 분석 결과
                print(f"[DEBUG] PDF 분석 직후:")
                print(f"  연도: {info.year}")
                print(f"  월: {info.month}")
                print(f"  분류: {info.subject}")
                print(f"  학년: {info.grade}")
        except Exception as e:
            print(f"[오류] PDF 분석 실패: {e}")
            info.confidence = 0.0
            
        return info
    
    def _analyze_hwp(self, filepath: str) -> ExtractedInfo:
        """
        HWP/HWPX 파일 분석 - 파일명 우선 전략
        
        HWP 본문 텍스트는 품질이 매우 불안정하므로:
        1. 파일명에서 연도/월 무조건 우선 사용
        2. 본문에서는 분류(과목)만 보조 추출
        """
        # 1단계: 파일명에서 먼저 정보 추출 (가장 신뢰할 수 있음)
        info = self._extract_from_filename(filepath)
        info.source = "filename"
        
        ext = Path(filepath).suffix.lower()
        
        # 2단계: 분류가 없는 경우에만 본문에서 추출 시도
        if not info.subject:
            try:
                content_text = ""
                if ext == '.hwp' and HAS_OLEFILE:
                    content_text = self._get_hwp_text_safe(filepath)
                elif ext == '.hwpx':
                    content_text = self._get_hwpx_text_safe(filepath)
                
                if content_text:
                    # 과목 키워드만 검색
                    for keyword in SUBJECT_SUBCATEGORIES:
                        if keyword in content_text:
                            info.subject = keyword
                            break
                    if not info.subject:
                        for keyword in SUBJECT_CATEGORIES:
                            if keyword in content_text:
                                info.subject = keyword
                                break
            except Exception:
                pass
        
        # 신뢰도 설정
        if info.year and info.month and info.subject:
            info.confidence = 0.9
        elif info.year and info.month:
            info.confidence = 0.7
        elif info.year and info.subject:
            info.confidence = 0.6
        else:
            info.confidence = 0.3
            
        return info
    
    def _get_hwp_text_safe(self, filepath: str) -> str:
        """HWP에서 안전하게 텍스트 추출 (메타데이터 제외)"""
        text = ""
        try:
            ole = olefile.OleFileIO(filepath)
            raw_text = self._extract_hwp_text_from_ole(ole)
            ole.close()
            
            if raw_text:
                # 메타데이터/편집정보 패턴 제거
                # Administrator, user, WIN32LE 등이 포함된 라인 제외
                lines = raw_text.split('\n')
                clean_lines = []
                for line in lines:
                    line_lower = line.lower()
                    # 메타데이터 패턴 제외
                    if any(skip in line_lower for skip in [
                        'administrator', 'win32', 'windows', 'user !',
                        '오전', '오후', '월요일', '화요일', '수요일', 
                        '목요일', '금요일', '토요일', '일요일'
                    ]):
                        continue
                    # 날짜+시간 패턴 제외 (편집일자)
                    if re.search(r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일.*\d{1,2}[:시]', line):
                        continue
                    clean_lines.append(line)
                text = '\n'.join(clean_lines)
        except Exception:
            pass
        return text
    
    def _get_hwpx_text_safe(self, filepath: str) -> str:
        """HWPX에서 안전하게 텍스트 추출"""
        all_text = []
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith('.xml') and 'content' in name.lower():
                        try:
                            content = zf.read(name)
                            text = self._extract_text_from_xml(content)
                            if text:
                                all_text.append(text)
                        except Exception:
                            pass
        except Exception:
            pass
        return '\n'.join(all_text)
    
    def _analyze_hwp_olefile(self, filepath: str, info: ExtractedInfo) -> ExtractedInfo:
        """
        HWP 분석 - pyhwp 우선 사용
        pyhwp가 없으면 olefile로 폴백
        """
        text = ""
        
        # 1순위: pyhwp 사용 (가장 정확)
        if HAS_PYHWP:
            try:
                import io
                import sys
                
                # pyhwp의 extract_text는 stdout으로 출력하므로 캡처
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                
                try:
                    hwp_extract_text(filepath)
                    text = sys.stdout.getvalue()
                finally:
                    sys.stdout = old_stdout
                
                if text:
                    print(f"[DEBUG] pyhwp 추출 성공! 텍스트 길이: {len(text)}")
                    print(f"[DEBUG] pyhwp 텍스트 (첫 300자): {text[:300]}")
            except Exception as e:
                print(f"[DEBUG] pyhwp 추출 실패: {e}")
                text = ""
        
        # 2순위: olefile 폴백
        if not text and HAS_OLEFILE:
            try:
                ole = olefile.OleFileIO(filepath)
                text = self._extract_hwp_text_from_ole(ole)
                ole.close()
                if text:
                    print(f"[DEBUG] olefile 추출 텍스트 (첫 300자): {text[:300]}")
            except Exception:
                pass
        
        # 텍스트 품질 검사 및 메타데이터 추출
        if text and self._check_text_quality(text):
            info = self._extract_metadata(text, info)
        else:
            # 품질 불량: 파일명에서 정보 추출
            info = self._extract_from_filename(filepath)
            info.source = "filename"
            if text:
                info.header_text = text[:200] + " (품질 불량)"
            
        return info
    
    def _extract_hwp_text_from_ole(self, ole) -> str:
        """
        OLE에서 HWP 텍스트 추출 - 확장된 버전
        머리말, 꼬리말, 표, 요약정보 등 모든 관련 스트림 읽기
        """
        text_parts = []
        
        # 읽어야 할 스트림 패턴들 (우선순위 순)
        stream_patterns = [
            'BodyText',      # 본문
            'Section',       # 섹션
            'BinData',       # 바이너리 데이터 (표 등)
            'DocInfo',       # 문서 정보
            'Scripts',       # 스크립트
            'XMLTemplate',   # XML 템플릿
            'DocOptions',    # 문서 옵션
        ]
        
        # 요약 정보 스트림 읽기 (메타데이터)
        try:
            if ole.exists('\x05HwpSummaryInformation'):
                try:
                    summary_data = ole.openstream('\x05HwpSummaryInformation').read()
                    summary_text = self._decode_hwp_summary(summary_data)
                    if summary_text:
                        text_parts.append(summary_text)
                except Exception:
                    pass
        except Exception:
            pass
        
        # 모든 스트림 탐색
        try:
            for entry in ole.listdir():
                entry_path = '/'.join(entry)
                
                # 관련 스트림인지 확인
                is_relevant = any(pattern in entry_path for pattern in stream_patterns)
                
                if is_relevant:
                    try:
                        data = ole.openstream(entry).read()
                        
                        # zlib 압축 해제 시도
                        try:
                            data = zlib.decompress(data, -15)
                        except Exception:
                            pass
                        
                        # 텍스트 디코딩
                        text = self._decode_hwp_body(data)
                        if text and len(text.strip()) > 5:
                            text_parts.append(text)
                    except Exception:
                        pass
        except Exception:
            pass
        
        # 모든 텍스트 합치기
        full_text = '\n'.join(text_parts)
        
        # 디버그 출력 (첫 500자)
        if full_text:
            print(f"[DEBUG] HWP 추출 텍스트 (첫 300자): {full_text[:300]}")
        
        return full_text
    
    def _decode_hwp_summary(self, data: bytes) -> str:
        """HWP 요약 정보 디코딩"""
        result = []
        
        # 다양한 인코딩 시도
        for encoding in ['utf-16-le', 'utf-8', 'cp949', 'euc-kr']:
            try:
                text = data.decode(encoding, errors='ignore')
                # 한글이 있는지 확인
                korean_count = sum(1 for c in text if '\uAC00' <= c <= '\uD7A3')
                if korean_count > 3:
                    # 제어 문자 제거
                    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                    return text.strip()
            except Exception:
                pass
        
        return ""
    
    def _decode_hwp_body(self, data: bytes) -> str:
        """HWP 본문 디코딩 - 개선된 버전"""
        result = []
        
        # 방법 1: UTF-16 LE 디코딩 시도
        for i in range(0, len(data) - 1, 2):
            try:
                char_code = data[i] | (data[i+1] << 8)
                # 한글 유니코드 범위: 0xAC00 ~ 0xD7A3
                # 기본 ASCII 범위: 0x20 ~ 0x7E
                if (0xAC00 <= char_code <= 0xD7A3 or  # 한글
                    0x20 <= char_code <= 0x7E or       # ASCII
                    0x3130 <= char_code <= 0x318F or   # 한글 자모
                    char_code in [0x0A, 0x0D, 0x09]):   # 줄바꿈, 탭
                    char = chr(char_code)
                    result.append(char)
            except Exception:
                pass
        
        text = ''.join(result)
        
        # 텍스트 정리
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)  # 제어 문자 제거
        text = re.sub(r'\s+', ' ', text)  # 연속 공백 정리
        
        return text.strip()
    
    def _check_text_quality(self, text: str) -> bool:
        """추출된 텍스트 품질 검사"""
        if not text or len(text) < 10:
            return False
        
        # 한글 비율 검사
        korean_count = sum(1 for c in text if '\uAC00' <= c <= '\uD7A3')
        total_chars = len(text.replace(' ', ''))
        
        if total_chars == 0:
            return False
        
        korean_ratio = korean_count / total_chars
        
        # 한글이 20% 이상이면 품질 양호
        return korean_ratio >= 0.2
    
    def _analyze_hwpx(self, filepath: str, info: ExtractedInfo) -> ExtractedInfo:
        """
        HWPX 분석 - 확장된 버전
        머리말, 꼬리말, 본문, 표 등 모든 XML 파일 읽기
        """
        all_text_parts = []
        
        # 읽어야 할 XML 파일 패턴들 (우선순위 순)
        xml_patterns = [
            'header',       # 머리말
            'footer',       # 꼬리말
            'section',      # 섹션
            'content',      # 본문
            'masterpage',   # 바탕쪽
            'settings',     # 설정
        ]
        
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                # 모든 XML 파일 순회
                for name in zf.namelist():
                    name_lower = name.lower()
                    
                    # XML 파일이면서 관련 패턴과 일치하는지 확인
                    if name.endswith('.xml'):
                        is_relevant = any(pattern in name_lower for pattern in xml_patterns)
                        
                        if is_relevant or 'contents' in name_lower:
                            try:
                                content = zf.read(name)
                                text = self._extract_text_from_xml(content)
                                if text and len(text.strip()) > 5:
                                    all_text_parts.append(text)
                            except Exception:
                                pass
        except Exception:
            pass
        
        # 모든 텍스트 합치기
        full_text = '\n'.join(all_text_parts)
        
        if full_text:
            print(f"[DEBUG] HWPX 추출 텍스트 (첫 300자): {full_text[:300]}")
            
            if self._check_text_quality(full_text):
                info = self._extract_metadata(full_text, info)
            else:
                # 품질 불량: 파일명에서 정보 추출
                info = self._extract_from_filename(filepath)
                info.source = "filename"
        else:
            # 텍스트 추출 실패: 파일명에서 정보 추출
            info = self._extract_from_filename(filepath)
            info.source = "filename"
            
        return info
    
    def _extract_text_from_xml(self, xml_content: bytes) -> str:
        """XML에서 텍스트 추출 - 개선된 버전"""
        try:
            # UTF-8로 디코딩
            text = xml_content.decode('utf-8', errors='ignore')
            
            # XML 태그 제거 (텍스트 내용만 추출)
            text = re.sub(r'<[^>]+>', ' ', text)
            
            # HTML 엔티티 변환
            text = text.replace('&lt;', '<').replace('&gt;', '>')
            text = text.replace('&amp;', '&').replace('&quot;', '"')
            text = text.replace('&nbsp;', ' ')
            
            # 연속 공백 정리
            text = re.sub(r'\s+', ' ', text)
            
            return text.strip()
        except Exception:
            return ""
    
    def _analyze_hwp_binary(self, filepath: str, info: ExtractedInfo) -> ExtractedInfo:
        """바이너리에서 텍스트 추출 - 품질 검사 포함"""
        extracted_text = ""
        
        try:
            with open(filepath, 'rb') as f:
                data = f.read(50000)
                
            for encoding in ['utf-16-le', 'utf-8', 'cp949', 'euc-kr']:
                try:
                    text = data.decode(encoding, errors='ignore')
                    if self._check_text_quality(text):
                        extracted_text = text
                        break
                except Exception:
                    pass
        except Exception:
            pass
        
        # 품질 검사 후 처리
        if extracted_text and self._check_text_quality(extracted_text):
            info = self._extract_metadata(extracted_text, info)
        else:
            # 품질 불량: 파일명에서만 정보 추출
            info = self._extract_from_filename(filepath)
            info.source = "filename"
            
        return info
    
    def _extract_subject_from_header(self, header_text: str, info: ExtractedInfo) -> ExtractedInfo:
        """상단 텍스트에서 분류 추출"""
        if not header_text:
            return info
            
        confidence = info.confidence
        keywords_to_search = self.custom_keywords if self.custom_keywords else SUBJECT_KEYWORDS
        
        # 1단계: 세분류 검색 (단어 경계 고려)
        found_sub = False
        
        for keyword in SUBJECT_SUBCATEGORIES:
            # 단어 경계 패턴 생성
            pattern = re.compile(r'(?:^|[\s\[\](){}【】「」『』《》<>·,.\-_])' + re.escape(keyword) + r'(?:$|[\s\[\](){}【】「」『』《》<>·,.\-_]|[0-9])')
            if pattern.search(header_text):
                info.subject_sub = keyword
                info.subject = keyword
                confidence += 0.35
                found_sub = True
                break
        
        # 단순 포함 검색 (경계 매칭 실패 시)
        if not found_sub:
            for keyword in SUBJECT_SUBCATEGORIES:
                if keyword in header_text:
                    info.subject_sub = keyword
                    info.subject = keyword
                    confidence += 0.3
                    found_sub = True
                    break
        
        # 2단계: 상위 분류 검색
        for keyword in SUBJECT_CATEGORIES:
            if keyword in header_text:
                info.subject_main = keyword
                if not found_sub:
                    info.subject = keyword
                    confidence += 0.25
                break
        
        # 3단계: 사용자 정의 키워드
        if not info.subject:
            for keyword in keywords_to_search:
                if keyword in header_text:
                    info.subject = keyword
                    confidence += 0.25
                    break
        
        # 4단계: 스마트 추출 (기존 키워드에서 못 찾은 경우)
        if not info.subject:
            smart_keyword = self._extract_smart_keyword(header_text)
            if smart_keyword:
                info.subject = smart_keyword
                info.is_smart_extracted = True  # 스마트 추출 표시
                confidence += 0.15  # 스마트 추출은 신뢰도 낮음
        
        info.confidence = min(confidence, 1.0)
        return info
    
    def _extract_smart_keyword(self, header_text: str) -> str:
        """문서 상단에서 스마트 키워드 추출"""
        if not header_text:
            return ""
        
        # 제외할 불용어 (의미 없는 단어들)
        stopwords = {
            '및', '의', '를', '을', '에', '가', '이', '은', '는', '로', '으로', '에서',
            '년', '월', '일', '제', '호', '차', '회', '분', '시', '때', '등', '중',
            '본', '당', '그', '이것', '저것', '것', '수', '것이', '위한', '대한', '관한',
            '안내', '문서', '파일', '자료', '작성', '담당', '내용',
        }
        
        extracted = ""
        
        # 방법 1: 괄호/대괄호 안의 텍스트 추출 (예: [물리학개론], 【화학실험】)
        bracket_patterns = [
            r'[\[【\[]([\uAC00-\uD7A3a-zA-Z0-9]+(?:\s*[\uAC00-\uD7A3a-zA-Z0-9]+)*)[\]】\]]',  # [텍스트], 【텍스트】
            r'[\(]([\uAC00-\uD7A3]{2,6})[\)]',  # (한글2-6자)
            r'[<《]([\uAC00-\uD7A3a-zA-Z0-9]+(?:\s*[\uAC00-\uD7A3a-zA-Z0-9]+)*)[>》]',  # <텍스트>, 《텍스트》
        ]
        
        for pattern in bracket_patterns:
            match = re.search(pattern, header_text)
            if match:
                candidate = match.group(1).strip()
                if 2 <= len(candidate) <= 15 and candidate not in stopwords:
                    return candidate
        
        # 방법 2: 첫 줄에서 핵심 단어 추출
        first_line = header_text.split('\n')[0].strip() if header_text else ""
        if first_line:
            # 콜론/하이픈 앞의 텍스트 (예: "물리학: 역학 기초" -> "물리학")
            colon_match = re.match(r'^([\uAC00-\uD7A3a-zA-Z0-9\s]{2,10})[:：\-]', first_line)
            if colon_match:
                candidate = colon_match.group(1).strip()
                if candidate and candidate not in stopwords:
                    return candidate
        
        # 방법 3: 한글 명사 추출 (2-4글자 한글 단어 중 첫 번째)
        korean_words = re.findall(r'[\uAC00-\uD7A3]{2,6}', header_text[:200])
        for word in korean_words:
            # 숫자가 포함된 단어나 일반적인 불용어 제외
            if word not in stopwords and not re.search(r'[0-9]', word):
                # 접미사로 끝나는 일반 단어 제외
                if not word.endswith(('하다', '되다', '입니다', '합니다', '있다', '없다')):
                    return word
        
        return extracted
    
    def _extract_date_from_text(self, text: str, info: ExtractedInfo) -> ExtractedInfo:
        """텍스트에서 연도/월 추출 - 문자열 검색 방식"""
        confidence = info.confidence
        
        # ========================================
        # 1단계: 연도 추출 (문자열 검색)
        # ========================================
        if not info.year:
            # "학년도" 검색
            if '학년도' in text:
                # "학년도" 앞의 4자리 숫자 찾기
                idx = text.find('학년도')
                if idx >= 4:
                    year_candidate = text[idx-4:idx]
                    if year_candidate.isdigit() and year_candidate.startswith('20'):
                        info.year = year_candidate + "학년도"
                        confidence += 0.3
            
            # "년" 검색 (학년도 못 찾은 경우)
            if not info.year and '년' in text:
                idx = text.find('년')
                if idx >= 4:
                    year_candidate = text[idx-4:idx]
                    if year_candidate.isdigit() and year_candidate.startswith('20'):
                        info.year = year_candidate
                        confidence += 0.25
            
            # 2020~2039 범위의 연도 직접 검색
            if not info.year:
                for year in range(2020, 2040):
                    year_str = str(year)
                    if year_str in text:
                        info.year = year_str
                        confidence += 0.15
                        break
        
        # ========================================
        # 2단계: 월 추출 (문자열 검색)
        # ========================================
        # "월" 검색
        if not info.month and '월' in text:
            idx = text.find('월')
            if idx >= 1:
                # 바로 앞 1~2자리가 숫자인지 확인
                if idx >= 2 and text[idx-2:idx].isdigit():
                    month_str = text[idx-2:idx]
                elif text[idx-1:idx].isdigit():
                    month_str = text[idx-1:idx]
                else:
                    month_str = None
                
                if month_str:
                    month_num = int(month_str)
                    if 1 <= month_num <= 12:
                        info.month = f"{month_num:02d}"
                        confidence += 0.2
        
        # 대학수학능력시험 키워드 → 11월
        if not info.month:
            suneung_keywords = ['대학수학능력시험', '수학능력시험', '능력시험', '수능']
            for keyword in suneung_keywords:
                if keyword in text:
                    info.month = "11"
                    confidence += 0.25
                    break
        
        info.confidence = min(confidence, 1.0)
        return info
    
    def _extract_from_filename(self, filepath: str) -> ExtractedInfo:
        """파일명에서 정보 추출 (개선된 버전)"""
        info = ExtractedInfo(source="filename")
        filename = Path(filepath).stem
        
        # ===== 연도 추출 =====
        # 1순위: 학년도
        haknundo_match = re.search(r'(20[0-9]{2})학년도', filename)
        if haknundo_match:
            info.year = haknundo_match.group(1) + "학년도"
        else:
            # 2순위: YYYY-MM 형태 (예: 2025-07)
            year_month_match = re.search(r'(20\d{2})[-_./](\d{1,2})', filename)
            if year_month_match:
                info.year = year_month_match.group(1)
                month = int(year_month_match.group(2))
                if 1 <= month <= 12:
                    info.month = f"{month:02d}"
            else:
                # 3순위: YYYY년 또는 YYYY만
                year_match = re.search(r'(20[0-9]{2})년?', filename)
                if year_match:
                    info.year = year_match.group(1)
        
        # ===== 월 추출 (아직 못 찾은 경우) =====
        if not info.month:
            # N월 형태
            month_match = re.search(r'(\d{1,2})월', filename)
            if month_match:
                month_num = int(month_match.group(1))
                if 1 <= month_num <= 12:
                    info.month = f"{month_num:02d}"
        
        # 수능 키워드 → 11월
        if not info.month:
            suneung_keywords = ['대학수학능력시험', '수학능력시험', '능력시험', '수능']
            for keyword in suneung_keywords:
                if keyword in filename:
                    info.month = "11"
                    break
        
        # ===== 분류 추출 =====
        for keyword in SUBJECT_SUBCATEGORIES:
            if keyword in filename:
                info.subject_sub = keyword
                info.subject = keyword
                break
                
        if not info.subject:
            for keyword in SUBJECT_CATEGORIES:
                if keyword in filename:
                    info.subject_main = keyword
                    info.subject = keyword
                    break
        
        # 범용 문서 키워드
        if not info.subject:
            for keyword in DOCUMENT_KEYWORDS:
                if keyword in filename:
                    info.subject = keyword
                    break
        
        # ===== 학년 추출 (확장) =====
        grade_patterns = [
            r'(고)\s*([1-3])',           # 고3, 고 3
            r'(중)\s*([1-3])',           # 중3, 중 3
            r'(고등학교)\s*([1-3])\s*학년',
            r'(중학교)\s*([1-3])\s*학년',
            r'(초등학교)\s*([1-6])\s*학년',
        ]
        
        for pattern in grade_patterns:
            match = re.search(pattern, filename)
            if match:
                prefix_full = match.group(1)
                num = match.group(2)
                
                if prefix_full in ['고', '고등학교']:
                    prefix = '고'
                elif prefix_full in ['중', '중학교']:
                    prefix = '중'
                elif prefix_full == '초등학교':
                    prefix = '초'
                else:
                    prefix = prefix_full[0]
                
                info.grade = f"{prefix}{num}"
                break
        
        return info
    
    def _merge_info(self, primary: ExtractedInfo, secondary: ExtractedInfo) -> ExtractedInfo:
        """
        정보 병합 - 파일명 정보 우선 정책
        파일명에서 추출된 정보(YYYY-MM 패턴 등)는 더 신뢰할 수 있으므로 우선 사용
        """
        # 파일명에서 추출된 정보가 있으면 우선 사용
        if secondary.source == "filename":
            # 연도: 파일명에 있으면 파일명 우선 (단, 학년도 형태가 아닌 경우)
            if secondary.year:
                if not primary.year or (secondary.month and not primary.month):
                    # 파일명에서 연도와 월이 함께 추출된 경우 (YYYY-MM 패턴)
                    primary.year = secondary.year
            
            # 월: 파일명에서 추출된 월이 있으면 우선 사용
            # (파일명 YYYY-MM 패턴은 매우 신뢰할 수 있음)
            if secondary.month:
                primary.month = secondary.month
            
            # 분류: 파일명의 세분류가 더 구체적이면 우선 사용
            if secondary.subject_sub:
                primary.subject_sub = secondary.subject_sub
                primary.subject = secondary.subject_sub
            elif secondary.subject and not primary.subject:
                primary.subject = secondary.subject
        else:
            # 기존 로직: primary가 없을 때만 secondary 사용
            if not primary.year and secondary.year:
                primary.year = secondary.year
            if not primary.month and secondary.month:
                primary.month = secondary.month
            if not primary.subject and secondary.subject:
                primary.subject = secondary.subject
            if not primary.subject_main and secondary.subject_main:
                primary.subject_main = secondary.subject_main
            if not primary.subject_sub and secondary.subject_sub:
                primary.subject_sub = secondary.subject_sub
        
        # 학년 병합 (있으면 사용)
        if not primary.grade and secondary.grade:
            primary.grade = secondary.grade
            
        return primary
    
    def _clean_filename(self, name: str) -> str:
        """파일명 정리"""
        # 금지 문자 제거
        for char in '<>:"/\\|?*':
            name = name.replace(char, '')
        
        name = re.sub(r'\s+', ' ', name).strip()
        return name[:100] if len(name) > 100 else name
    
    def generate_new_name(self, entry: FileEntry, pattern: str, index: int = 0, total: int = 0) -> str:
        """새 파일명 생성"""
        info = entry.extracted_info
        seq_format = f"{index + 1:03d}" if total >= 100 else f"{index + 1:02d}"
        
        replacements = {
            "{Year}": info.year or "XXXX",
            "{Month}": info.month or "XX",
            "{Subject}": info.subject or "기타",
            "{SubjectMain}": info.subject_main or info.subject or "기타",
            "{SubjectSub}": info.subject_sub or "",
            "{Original}": entry.original_name,
            "{Seq}": seq_format,
            "{Grade}": info.grade or "",  # 학년 (고1, 고2, 고3 등)
        }
        
        new_name = pattern
        for key, value in replacements.items():
            new_name = new_name.replace(key, value)
        
        new_name = self._clean_filename(new_name)
        new_name = re.sub(r'_+', '_', new_name)
        new_name = re.sub(r'-+', '-', new_name)
        return new_name.strip('_- ')
    
    def generate_all_names(self, entries: List[FileEntry], pattern: str) -> List[FileEntry]:
        """모든 파일 이름 생성"""
        total = len(entries)
        for i, entry in enumerate(entries):
            entry.order = i
            entry.proposed_name = self.generate_new_name(entry, pattern, i, total)
        return entries
    
    def check_duplicates(self, entries: List[FileEntry], dest_folder: Optional[str] = None) -> List[FileEntry]:
        """중복 확인"""
        name_counts: Dict[tuple, List[FileEntry]] = {}
        
        for entry in entries:
            full_name = entry.proposed_name + entry.extension
            dir_path = dest_folder or str(Path(entry.original_path).parent)
            key = (dir_path, full_name.lower())
            
            if key not in name_counts:
                name_counts[key] = []
            name_counts[key].append(entry)
        
        # 목록 내 중복 처리
        for dup_entries in name_counts.values():
            if len(dup_entries) > 1:
                for i, entry in enumerate(dup_entries[1:], 1):
                    entry.proposed_name = f"{entry.proposed_name}({i})"
                    entry.status = FileStatus.DUPLICATE
        
        # 기존 파일과의 중복 처리
        for entry in entries:
            target_dir = Path(dest_folder) if dest_folder else Path(entry.original_path).parent
            new_path = target_dir / (entry.proposed_name + entry.extension)
                
            if new_path.exists() and str(new_path) != entry.original_path:
                counter = 1
                while True:
                    test_name = f"{entry.proposed_name}({counter})"
                    test_path = target_dir / (test_name + entry.extension)
                    if not test_path.exists():
                        entry.proposed_name = test_name
                        entry.status = FileStatus.DUPLICATE
                        break
                    counter += 1
        
        return entries
    
    def execute_rename(self, entries: List[FileEntry], dest_folder: Optional[str] = None) -> Tuple[int, int, List[str]]:
        """이름 변경 실행"""
        success_count = 0
        fail_count = 0
        errors = []
        
        if dest_folder:
            Path(dest_folder).mkdir(parents=True, exist_ok=True)
        
        self.current_transaction = RenameTransaction(timestamp=datetime.now().isoformat())
        
        for entry in entries:
            if entry.status == FileStatus.ERROR:
                continue
                
            try:
                old_path = Path(entry.original_path)
                new_name = entry.proposed_name + entry.extension
                
                if dest_folder:
                    new_path = Path(dest_folder) / new_name
                    shutil.copy2(str(old_path), str(new_path))
                    operation_type = 'copy'
                else:
                    new_path = old_path.parent / new_name
                    if old_path == new_path:
                        continue
                    shutil.move(str(old_path), str(new_path))
                    operation_type = 'rename'
                
                self.current_transaction.operations.append({
                    'type': operation_type,
                    'old_path': str(old_path),
                    'new_path': str(new_path)
                })
                
                entry.status = FileStatus.RENAMED
                entry.original_path = str(new_path)
                success_count += 1
                
            except Exception as e:
                entry.status = FileStatus.ERROR
                entry.error_message = str(e)
                errors.append(f"{entry.original_name}: {e}")
                fail_count += 1
        
        if self.current_transaction.operations:
            self._save_transaction()
        
        return success_count, fail_count, errors
    
    def _save_transaction(self):
        """트랜잭션 저장"""
        if not self.current_transaction:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"transaction_{timestamp}.json"
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(self.current_transaction.to_dict(), f, ensure_ascii=False, indent=2)
    
    def get_last_transaction(self) -> Optional[RenameTransaction]:
        """마지막 트랜잭션"""
        log_files = sorted(self.log_dir.glob("transaction_*.json"), reverse=True)
        
        if not log_files:
            return None
            
        try:
            with open(log_files[0], 'r', encoding='utf-8') as f:
                data = json.load(f)
                return RenameTransaction(**data)
        except Exception:
            return None
    
    def undo_last_rename(self) -> Tuple[bool, str]:
        """되돌리기"""
        transaction = self.get_last_transaction()
        
        if not transaction:
            return False, "되돌릴 수 있는 작업이 없습니다."
        
        errors = []
        success_count = 0
        
        for op in reversed(transaction.operations):
            try:
                old_path = Path(op['old_path'])
                new_path = Path(op['new_path'])
                op_type = op.get('type', 'rename')
                
                if new_path.exists():
                    if op_type == 'copy':
                        new_path.unlink()
                    else:
                        shutil.move(str(new_path), str(old_path))
                    success_count += 1
                else:
                    errors.append(f"파일 없음: {new_path.name}")
                    
            except Exception as e:
                errors.append(f"{op['new_path']}: {e}")
        
        # 로그 파일 삭제
        log_files = sorted(self.log_dir.glob("transaction_*.json"), reverse=True)
        if log_files:
            log_files[0].unlink()
        
        if errors:
            return False, f"{success_count}개 복원, 오류: " + "; ".join(errors)
        return True, f"{success_count}개 파일이 복원되었습니다."
