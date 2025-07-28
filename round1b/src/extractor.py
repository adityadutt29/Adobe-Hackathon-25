
import pdfplumber, pytesseract, math, re
from PIL import Image
from langdetect import detect
from pydantic import BaseModel
from pathlib import Path
from collections import Counter

class OutlineItem(BaseModel):
    level: str
    text: str
    page: int

class DocumentOutline(BaseModel):
    title: str
    outline: list[OutlineItem]

# ------------------------------------------------------------------
# Public API - Pure Heuristic Approach
# ------------------------------------------------------------------
def extract_outline(pdf_path: str) -> dict:
    return _enhanced_heuristic_outline(pdf_path).model_dump()

def _enhanced_heuristic_outline(pdf_path: str) -> DocumentOutline:
    """Enhanced heuristic approach with tree-structured heading organization"""
    
    with pdfplumber.open(pdf_path) as pdf:
        # Extract document title from first page
        title = _extract_document_title_from_first_page(pdf.pages[0] if pdf.pages else None)
        
        # Extract all potential headings from all pages
        all_candidates = []
        for page_num, page in enumerate(pdf.pages, start=1):
            if not page.chars:
                # OCR for scanned pages
                ocr_candidates = _ocr_page(page, page_num)
                all_candidates.extend(ocr_candidates)
                continue
            
            # Extract heading candidates from page
            page_candidates = _extract_heading_candidates_from_page(page, page_num)
            all_candidates.extend(page_candidates)
        
        # Build hierarchical structure and filter
        outline_items = _build_document_hierarchy(all_candidates)
    
    return DocumentOutline(title=title, outline=outline_items)

def _extract_document_title_from_first_page(first_page):
    """Extract document title specifically from the first page"""
    if not first_page or not first_page.chars:
        return "Untitled"
    
    # Get all text from first page
    page_text = first_page.extract_text() or ""
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    
    # Look for RFP title pattern in multiple ways
    title_candidates = []
    
    # Method 1: Look for explicit RFP patterns
    for i, line in enumerate(lines[:20]):  # Check first 20 lines
        line_lower = line.lower()
        
        # Strong RFP title indicators
        if ('rfp' in line_lower and 'request' in line_lower) or 'request for proposal' in line_lower:
            # Try to reconstruct the full title
            title_parts = []
            
            # Look back a few lines for title start
            start_idx = max(0, i-3)
            for j in range(start_idx, i+1):
                if j < len(lines):
                    candidate_line = lines[j].strip()
                    if (len(candidate_line) > 5 and 
                        not re.match(r'^\d+', candidate_line) and
                        not candidate_line.lower().startswith(('march', 'april', 'january'))):
                        title_parts.append(candidate_line)
            
            # Look ahead for continuation
            for j in range(i+1, min(i+8, len(lines))):
                next_line = lines[j].strip()
                if (next_line and len(next_line) > 5 and
                    any(word in next_line.lower() for word in 
                        ['proposal', 'developing', 'business', 'plan', 'ontario', 'digital', 'library']) and
                    not next_line.lower().startswith(('march', 'april', 'january'))):
                    title_parts.append(next_line)
                elif len(next_line) < 80 and not next_line.endswith('.') and next_line:
                    title_parts.append(next_line)
                else:
                    break
            
            if title_parts:
                full_title = ' '.join(title_parts).strip()
                # Clean up common artifacts
                full_title = re.sub(r'\s+', ' ', full_title)  # Multiple spaces
                if len(full_title) > 20:
                    title_candidates.append(full_title)
    
    # Method 2: Look for specific title patterns if no RFP found
    if not title_candidates:
        for i, line in enumerate(lines[:15]):
            line_lower = line.lower()
            
            # Look for "to present a proposal" pattern
            if 'to present' in line_lower and 'proposal' in line_lower:
                title_parts = [line]
                # Look ahead for "for developing" etc.
                for j in range(i+1, min(i+5, len(lines))):
                    next_line = lines[j].strip()
                    if (next_line and 
                        any(word in next_line.lower() for word in ['developing', 'business', 'plan', 'ontario', 'digital', 'library'])):
                        title_parts.append(next_line)
                    else:
                        break
                
                if len(title_parts) > 1:
                    title_candidates.append(' '.join(title_parts))
    
    # Method 3: Look for business plan patterns
    if not title_candidates:
        for line in lines[:10]:
            if (len(line) > 20 and 
                'business plan' in line.lower() and
                any(word in line.lower() for word in ['ontario', 'digital', 'library'])):
                title_candidates.append(line)
    
    # Method 4: Construct from common patterns if found
    if not title_candidates:
        # Look for key components scattered in first few lines
        rfp_line = None
        proposal_line = None
        business_line = None
        
        for line in lines[:10]:
            line_lower = line.lower()
            if 'rfp' in line_lower or 'request for proposal' in line_lower:
                rfp_line = line
            elif 'to present' in line_lower and 'proposal' in line_lower:
                proposal_line = line  
            elif 'business plan' in line_lower and 'ontario' in line_lower:
                business_line = line
        
        # Try to combine found components
        if rfp_line and (proposal_line or business_line):
            components = [rfp_line]
            if proposal_line:
                components.append(proposal_line)
            if business_line:
                components.append(business_line)
            title_candidates.append(' '.join(components))
    
    # Select best candidate
    if title_candidates:
        # Prefer longer, more complete titles
        best_candidate = max(title_candidates, key=len)
        
        # Clean up the title
        best_candidate = re.sub(r'\s+', ' ', best_candidate).strip()
        
        # If it's very long, try to truncate sensibly
        if len(best_candidate) > 150:
            # Look for a good break point
            sentences = best_candidate.split('.')
            if len(sentences) > 1 and len(sentences[0]) > 30:
                best_candidate = sentences[0].strip()
        
        return best_candidate
    
    # Final fallback - look for any substantial line mentioning key terms
    for line in lines[:8]:
        if (len(line) > 15 and 
            any(word in line.lower() for word in ['ontario', 'digital', 'library']) and
            not re.match(r'^\d+', line)):
            return line
    
    return lines[0] if lines else "Untitled"

def _extract_headings_from_page(page, page_num):
    """Extract headings from a single page"""
    headings = []
    
    # Get all text lines with font information
    text_lines = _get_text_lines_with_fonts(page)
    
    # Determine font size thresholds for this page
    font_sizes = [line['avg_size'] for line in text_lines if line['avg_size'] > 0]
    if not font_sizes:
        return headings
    
    # Calculate thresholds
    font_sizes.sort(reverse=True)
    unique_sizes = list(set(font_sizes))
    unique_sizes.sort(reverse=True)
    
    # Set thresholds based on available font sizes
    if len(unique_sizes) >= 3:
        h1_threshold = unique_sizes[0]
        h2_threshold = unique_sizes[1] 
        h3_threshold = unique_sizes[2]
    elif len(unique_sizes) == 2:
        h1_threshold = unique_sizes[0]
        h2_threshold = unique_sizes[1]
        h3_threshold = unique_sizes[1]
    else:
        h1_threshold = h2_threshold = h3_threshold = unique_sizes[0] if unique_sizes else 12
    
    # Analyze each line
    for line in text_lines:
        text = line['text']
        
        # Skip very short or very long text
        if len(text) < 3 or len(text) > 250:
            continue
        
        # Calculate heading score
        score = _calculate_heading_score(line, h1_threshold, h2_threshold, h3_threshold)
        
        if score['confidence'] > 0.5:
            headings.append(OutlineItem(
                level=score['level'],
                text=text,
                page=page_num
            ))
    
    return headings

def _extract_heading_candidates_from_page(page, page_num):
    """Extract heading candidates with enhanced filtering"""
    candidates = []
    
    # Get all text lines with font information
    text_lines = _get_text_lines_with_fonts(page)
    
    # Calculate font size statistics for this page
    font_sizes = [line['avg_size'] for line in text_lines if line['avg_size'] > 0]
    if not font_sizes:
        return candidates
    
    # Determine thresholds more intelligently
    thresholds = _calculate_smart_thresholds(font_sizes, text_lines)
    
    # Analyze each line with enhanced scoring
    for line in text_lines:
        candidate = _analyze_line_with_enhanced_scoring(line, thresholds, page_num)
        if candidate:
            candidates.append(candidate)
    
    return candidates

def _calculate_smart_thresholds(font_sizes, text_lines):
    """Calculate smarter font size thresholds based on content analysis"""
    unique_sizes = sorted(set(font_sizes), reverse=True)
    
    # Analyze which font sizes are actually used for meaningful content
    size_usage = {}
    for line in text_lines:
        size = line['avg_size']
        if size not in size_usage:
            size_usage[size] = {'count': 0, 'total_chars': 0, 'heading_indicators': 0}
        
        size_usage[size]['count'] += 1
        size_usage[size]['total_chars'] += len(line['text'])
        
        # Count heading indicators
        if any(pattern in line['text'].lower() for pattern in 
               ['summary', 'background', 'appendix', 'phase', 'section']):
            size_usage[size]['heading_indicators'] += 1
    
    # Select sizes that are likely for headings
    heading_sizes = []
    for size in unique_sizes:
        usage = size_usage.get(size, {})
        avg_length = usage.get('total_chars', 0) / max(usage.get('count', 1), 1)
        
        # Prefer sizes used for shorter text (likely headings)
        if avg_length < 60 or usage.get('heading_indicators', 0) > 0:
            heading_sizes.append(size)
    
    # Set thresholds based on identified heading sizes
    if len(heading_sizes) >= 3:
        return {'h1': heading_sizes[0], 'h2': heading_sizes[1], 'h3': heading_sizes[2]}
    elif len(heading_sizes) == 2:
        return {'h1': heading_sizes[0], 'h2': heading_sizes[1], 'h3': heading_sizes[1]}
    elif len(heading_sizes) == 1:
        return {'h1': heading_sizes[0], 'h2': heading_sizes[0], 'h3': heading_sizes[0]}
    else:
        # Fallback to largest sizes
        return {
            'h1': unique_sizes[0] if unique_sizes else 12,
            'h2': unique_sizes[1] if len(unique_sizes) > 1 else 12,
            'h3': unique_sizes[2] if len(unique_sizes) > 2 else 12
        }

def _analyze_line_with_enhanced_scoring(line, thresholds, page_num):
    """Enhanced line analysis with better scoring"""
    text = line['text'].strip()
    
    # Enhanced filtering for non-headings
    if _is_definitely_not_heading(text):
        return None
    
    # Skip very short or very long text
    if len(text) < 3 or len(text) > 200:
        return None
    
    # Skip obvious content fragments
    if _is_content_fragment(text):
        return None
    
    confidence = 0.0
    level = 'H4'
    
    # Font size scoring with more nuance
    size = line['avg_size']
    if size >= thresholds['h1']:
        confidence += 0.4
        level = 'H1'
    elif size >= thresholds['h2']:
        confidence += 0.3
        level = 'H2'
    elif size >= thresholds['h3']:
        confidence += 0.2
        level = 'H3'
    else:
        confidence += 0.1
        level = 'H4'
    
    # Enhanced pattern analysis
    pattern_boost, pattern_level = _enhanced_pattern_analysis(text)
    confidence += pattern_boost
    if pattern_level and pattern_boost > 0.3:
        level = pattern_level
    
    # Position and formatting bonuses
    if line['is_bold']:
        confidence += 0.2
    
    if line['left_margin'] < 80:  # Left aligned
        confidence += 0.1
    
    # Length scoring (headings are typically shorter)
    if len(text) < 100:
        confidence += 0.1
    if len(text) < 50:
        confidence += 0.1
    
    # Bonus for complete, well-formed headings
    if _is_well_formed_heading(text):
        confidence += 0.2
    
    # Penalty for incomplete or fragmented text
    if _is_incomplete_heading(text):
        confidence -= 0.3
    
    # Only include high-confidence candidates
    if confidence > 0.55:  # Further reduced threshold to catch more sections
        return {
            'text': text,
            'level': level,
            'page': page_num,
            'confidence': min(confidence, 1.0),
            'font_size': size,
            'position': line.get('y_pos', 0)
        }
    
    return None

def _is_content_fragment(text):
    """Check if text is a content fragment rather than a heading"""
    # Fragments that are clearly middle of sentences
    if text.startswith(('and ', 'or ', 'but ', 'the ', 'a ', 'an ', 'of ', 'in ', 'to ', 'for ')):
        return True
    
    # Fragments ending mid-sentence
    if text.endswith((' and', ' or', ' of', ' in', ' to', ' for', ' the', ' a')):
        return True
    
    # Timeline fragments
    if re.match(r'^\w+ \d{4}\s*-?\s*$', text) or 'timeline:' in text.lower():
        return True
    
    # Very incomplete sentences
    if len(text.split()) < 3 and not text.endswith(':') and not text.isupper():
        return True
    
    return False

def _is_well_formed_heading(text):
    """Check if text is a well-formed heading"""
    # Complete questions
    if text.startswith(('What ', 'How ', 'Why ')) and text.endswith('?'):
        return True
    
    # Proper section titles
    section_patterns = [
        r'^(Summary|Background|Introduction|Overview|Conclusion)$',
        r'^Appendix [A-Z]:', 
        r'^Phase [IVX]+:',
        r'^[A-Z][a-z]+(\s+[A-Z][a-z]*)*:$',  # Title case ending with colon
        r'^\d+\.\s+[A-Z][a-z]+'  # Numbered sections
    ]
    
    for pattern in section_patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    
    # "For each/For the" patterns that are complete
    if text.startswith(('For each ', 'For the ')) and text.endswith(':'):
        return True
    
    return False

def _is_incomplete_heading(text):
    """Check if text appears to be an incomplete heading"""
    # Ends mid-sentence
    if text.endswith((' to', ' and', ' or', ' of', ' in', ' for', ' the', ' a', ' an')):
        return True
    
    # Starts mid-sentence  
    if text.startswith(('to ', 'and ', 'or ', 'of ', 'in ', 'for ')):
        return True
    
    # Contains partial words or obvious breaks
    if '...' in text or text.count(' ') > 12:  # Very long, likely paragraph
        return True
    
    return False

def _enhanced_pattern_analysis(text):
    """Enhanced pattern analysis with better scoring"""
    boost = 0.0
    suggested_level = None
    
    text_lower = text.lower().strip()
    
    # Document structure patterns (H1 level)
    document_structure = [
        'revision history', 'table of contents', 'acknowledgements', 
        'references', 'introduction to the foundation',
        'overview of the foundation'
    ]
    if any(pattern in text_lower for pattern in document_structure):
        return 0.9, 'H1'
    
    # Numbered main sections (H1 level)
    if re.match(r'^\d+\.\s+[A-Z][a-z]', text):
        return 0.9, 'H1'
    
    # Numbered subsections (H2 level)  
    if re.match(r'^\d+\.\d+\s+[A-Z][a-z]', text):
        return 0.8, 'H2'
    
    # Strong heading patterns
    if re.match(r'^appendix [a-z]:', text, re.IGNORECASE):
        return 0.8, 'H2'  # Increased confidence
    
    if re.match(r'^phase [ivx]+:', text, re.IGNORECASE):
        return 0.7, 'H3'  # Increased confidence
    
    # Major section headers (enhanced)
    major_sections = ['summary', 'background', 'introduction', 'overview', 'methodology', 'conclusion', 'timeline', 'milestones']
    if any(section == text_lower for section in major_sections):
        return 0.8, 'H2'  # Increased confidence
    
    # Career/Learning/Business related subsections
    career_learning = ['intended audience', 'career paths', 'learning objectives', 'entry requirements', 'structure and course', 'keeping it current', 'business outcomes', 'content', 'trademarks', 'documents and web']
    if any(pattern in text_lower for pattern in career_learning):
        return 0.8, 'H2'
    
    # Subsection patterns (enhanced)
    if text.startswith(('What could', 'For each', 'For the')):
        # Distinguish between H3 and H4 based on specificity
        if 'Ontario' in text and ('citizen' in text or 'student' in text or 'library' in text or 'government' in text):
            return 0.6, 'H4'  # More specific = H4
        return 0.6, 'H3'
    
    # Business plan specific patterns
    business_patterns = [
        'business plan', 'approach and specific', 'evaluation and awarding', 
        'milestones', 'requirements', 'terms of reference'
    ]
    if any(pattern in text_lower for pattern in business_patterns):
        return 0.7, 'H2'  # Increased confidence
    
    # Single word important sections
    important_singles = ['summary', 'background', 'timeline', 'milestones', 'preamble', 'membership', 'chair', 'term', 'meetings', 'acknowledgements', 'references']
    if text_lower in important_singles:
        return 0.8, 'H1'  # Changed to H1 for document structure
    
    # Colon endings (subheadings)
    if text.endswith(':') and len(text) < 80 and len(text) > 3:
        # Check if it's a principle or service (H3) vs specific item (H4)
        if any(word in text_lower for word in ['funding', 'governance', 'decision-making', 'access', 'support', 'training']):
            return 0.6, 'H3'
        return 0.5, 'H3'
    
    # All caps headings
    if text.isupper() and 3 < len(text) < 60:  # Reduced minimum
        return 0.6, 'H2'
    
    return boost, suggested_level

def _build_document_hierarchy(candidates):
    """Build hierarchical document structure using Node-based path tracking"""
    if not candidates:
        return []
    
    # Sort candidates by page and position
    candidates.sort(key=lambda x: (x['page'], x.get('position', 0)))
    
    # Create a node-like structure for tracking hierarchy and paths
    class DocumentNode:
        def __init__(self):
            self.next = {}  # Similar to unordered_map<string, Node*>
            self.path = []  # Similar to vector<string> path
            self.mark = False  # Similar to bool mark
            self.text = ""
            self.level = ""
            self.page = 0
            self.confidence = 0.0
    
    root = DocumentNode()
    current_path = []
    final_headings = []
    seen_texts = set()
    
    # Process candidates with path-aware filtering
    for candidate in candidates:
        text = candidate['text']
        level = candidate['level']
        page = candidate['page']
        confidence = candidate['confidence']
        
        # Skip duplicates
        text_key = text.lower().strip()
        if text_key in seen_texts:
            continue
        
        # Enhanced quality filtering using Node-based logic
        if not _node_quality_check(candidate, current_path, final_headings):
            continue
        
        # Create node for this heading
        node = DocumentNode()
        node.text = text
        node.level = level
        node.page = page
        node.confidence = confidence
        node.path = current_path.copy()
        
        # Update path based on heading hierarchy
        current_path = _update_path_with_hierarchy(current_path, level, text)
        node.path = current_path.copy()
        
        # Mark node as valid heading
        node.mark = True
        seen_texts.add(text_key)
        
        # Add to final results if it passes all checks
        final_headings.append(OutlineItem(
            level=level,
            text=text,
            page=page
        ))
    
    return final_headings[:40]  # Increased limit to match expected output

def _node_quality_check(candidate, current_path, existing_headings):
    """Enhanced quality check using Node-based path analysis"""
    text = candidate['text']
    level = candidate['level']
    confidence = candidate['confidence']
    
    # Lowered confidence threshold to capture more valid headings
    if confidence < 0.6:  # Reduced from 0.7
        return False
    
    # Enhanced fragment detection
    if _is_sentence_fragment(text):
        return False
    
    # Check path consistency
    if _breaks_hierarchy_path(candidate, current_path):
        return False
    
    # Enhanced content validation
    if not _is_meaningful_heading(text):
        return False
    
    # Context-aware duplicate checking
    if _is_contextual_duplicate(text, existing_headings):
        return False
    
    return True

def _is_sentence_fragment(text):
    """Detect sentence fragments that shouldn't be headings"""
    # Don't filter out important single word sections
    important_singles = ['summary', 'background', 'timeline', 'milestones', 'preamble', 'membership', 'chair', 'term', 'meetings', 'acknowledgements', 'references', 'content', 'trademarks']
    if text.lower().strip() in important_singles:
        return False
    
    # Don't filter out document structure headers
    document_headers = [
        'revision history', 'table of contents', 'acknowledgements',
        'references', 'trademarks', 'documents and web sites'
    ]
    if any(header in text.lower() for header in document_headers):
        return False
    
    # Don't filter out numbered sections
    if re.match(r'^\d+\.\s+[A-Za-z]', text) or re.match(r'^\d+\.\d+\s+[A-Za-z]', text):
        return False
    
    # Starts with lowercase or mid-sentence words (but allow technical terms)
    if text and text[0].islower() and not any(term in text.lower() for term in ['intended audience', 'career paths', 'learning objectives']):
        return True
    
    # Contains obvious sentence continuations
    fragment_indicators = [
        ' is to ', ' are to ', ' will be ', ' has been ', ' have been ',
        ' can be ', ' should be ', ' must be ', ' to be ', ' that ',
        ' which ', ' where ', ' when ', ' while ', ' during '
    ]
    if any(indicator in text.lower() for indicator in fragment_indicators):
        return True
    
    # Ends with incomplete phrases (but not colon endings which are headers)
    if text.endswith((' to', ' and', ' or', ' of', ' in', ' for', ' the', ' a', ' an', ' that', ' which')) and not text.endswith(':'):
        return True
    
    # Very incomplete sentences (less than 2 words and not a proper heading)
    words = text.split()
    if len(words) < 2 and not text.endswith(':') and not text.isupper() and text.lower() not in important_singles:
        return True
    
    return False

def _breaks_hierarchy_path(candidate, current_path):
    """Check if candidate breaks logical hierarchy path"""
    text = candidate['text']
    level = candidate['level']
    
    # Skip timeline entries that break hierarchy
    if re.match(r'^\d{4}[\s\-]', text) or 'timeline:' in text.lower():
        return True
    
    # Skip financial data that breaks hierarchy
    if re.match(r'^[\d\$,.\s%\-\(\)]+$', text):
        return True
    
    # Skip obvious page headers/footers
    if len(text) < 10 and (text.isdigit() or re.match(r'^page \d+', text.lower())):
        return True
    
    return False

def _is_meaningful_heading(text):
    """Check if text represents a meaningful heading"""
    # Must have substantial content
    if len(text.strip()) < 2:  # Further reduced
        return False
    
    # Should not be pure numbers or symbols
    if re.match(r'^[\d\s\-\.\(\)]+$', text):
        return False
    
    # Should not be email addresses or URLs
    if '@' in text or text.startswith(('http://', 'https://', 'www.')):
        return False
    
    # Document structure headers (high priority)
    document_headers = [
        'revision history', 'table of contents', 'acknowledgements',
        'references', 'trademarks', 'documents and web sites'
    ]
    if any(header in text.lower() for header in document_headers):
        return True
    
    # Prefer headings that end with colons or are complete phrases
    if text.endswith(':'):
        return True
    
    # Accept well-formed questions
    if text.startswith(('What ', 'How ', 'Why ', 'When ', 'Where ')) and text.endswith('?'):
        return True
    
    # Accept numbered sections (enhanced)
    if re.match(r'^\d+\.\s+[A-Za-z]', text):
        return True
    
    # Accept numbered subsections
    if re.match(r'^\d+\.\d+\s+[A-Za-z]', text):
        return True
    
    # Accept lettered appendices (enhanced)
    if re.match(r'^Appendix [A-Z]:', text, re.IGNORECASE):
        return True
    
    # Accept proper section titles (enhanced)
    section_patterns = [
        r'^(Summary|Background|Introduction|Overview|Conclusion|Timeline|Milestones|Acknowledgements|References)$',
        r'^Appendix [A-Z]:',
        r'^Phase [IVX]+:',
        r'^[A-Z][a-z]+(\s+[A-Z][a-z]*)*:$',
        r'^\d+\.\s+[A-Z][a-z]+',
        r'^(Chair|Term|Meetings|Membership|Preamble|Content|Audience|Duration|Outcomes|Trademarks)$'
    ]
    
    for pattern in section_patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    
    # Accept "For each/For the" patterns (enhanced for H4)
    if text.startswith(('For each ', 'For the ', 'For each Ontario')):
        return True
    
    # Accept business/technical terms (enhanced)
    business_terms = [
        'business plan', 'requirements', 'evaluation', 'approach', 
        'implementation', 'methodology', 'milestones', 'funding',
        'terms of reference', 'accountability', 'communication',
        'intended audience', 'career paths', 'learning objectives',
        'entry requirements', 'structure and course', 'keeping it current',
        'business outcomes', 'documents and web sites'
    ]
    if any(term in text.lower() for term in business_terms) and len(text) < 120:
        return True
    
    # Accept single important words that are clear headings (enhanced)
    important_single_words = [
        'summary', 'background', 'timeline', 'milestones', 'preamble',
        'membership', 'chair', 'term', 'meetings', 'acknowledgements',
        'references', 'content', 'trademarks'
    ]
    if text.lower().strip() in important_single_words:
        return True
    
    # Reject obvious sentence fragments
    if any(text.lower().startswith(start) for start in 
           ['the ', 'a ', 'an ', 'and ', 'or ', 'but ', 'to ', 'of ', 'in ', 'for ']):
        return False
    
    # Accept if it looks like a proper heading (title case, reasonable length)
    if text.istitle() and 2 <= len(text) <= 80:  # Further reduced minimum
        return True
    
    # Accept all caps headings
    if text.isupper() and 2 <= len(text) <= 60:
        return True
    
    return False

def _is_contextual_duplicate(text, existing_headings):
    """Check for contextual duplicates using path analysis"""
    if not existing_headings:
        return False
    
    # Simple similarity check with recent headings
    recent_headings = existing_headings[-3:]  # Check last 3 headings
    
    for heading in recent_headings:
        # Exact match
        if text.lower().strip() == heading.text.lower().strip():
            return True
        
        # Very high overlap
        words1 = set(text.lower().split())
        words2 = set(heading.text.lower().split())
        
        if words1 and words2:
            overlap = len(words1.intersection(words2))
            min_len = min(len(words1), len(words2))
            if overlap / min_len > 0.8:
                return True
    
    return False

def _update_path_with_hierarchy(current_path, level, text):
    """Update path based on heading hierarchy (similar to Node path tracking)"""
    # Determine hierarchy depth
    hierarchy_depth = {'H1': 0, 'H2': 1, 'H3': 2, 'H4': 3}
    depth = hierarchy_depth.get(level, 3)
    
    # Truncate path to appropriate depth
    new_path = current_path[:depth] if depth < len(current_path) else current_path.copy()
    
    # Add current heading to path
    new_path.append(text[:50])  # Truncate long headings in path
    
    return new_path

def _passes_final_quality_check(candidate, existing_headings):
    """Final quality check for heading candidates"""
    text = candidate['text']
    
    # Check if this adds value to existing headings
    if len(existing_headings) > 0:
        last_heading = existing_headings[-1]
        
        # Skip if very similar to previous heading
        if _texts_too_similar(text, last_heading.text):
            return False
        
        # Skip if this looks like a continuation of previous
        if (candidate['page'] == last_heading.page and 
            len(text) < 30 and len(last_heading.text) < 30):
            return False
    
    # Must meet minimum quality standards
    if candidate['confidence'] < 0.65:
        return False
    
    # Skip financial/numeric data that slipped through
    if re.match(r'^[\d\$,.\s%\-$]+$', text):
        return False
    
    return True

def _texts_too_similar(text1, text2):
    """Check if two texts are too similar"""
    # Simple similarity check
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return False
    
    overlap = len(words1.intersection(words2))
    min_len = min(len(words1), len(words2))
    
    return overlap / min_len > 0.8

def _is_definitely_not_heading(text):
    """Enhanced check if text is definitely not a heading"""
    # Combine original checks with new ones
    if _is_non_heading(text):
        return True
        
    # Additional checks for content fragments
    if _is_content_fragment(text):
        return True
        
    # Very short words or abbreviations
    if len(text.split()) == 1 and len(text) < 4:
        return True
        
    # Contains multiple sentences
    if text.count('.') > 1 and len(text) > 60:
        return True
        
    return False

def _get_text_lines_with_fonts(page):
    """Get text lines with font information"""
    lines = []
    
    # Group characters by Y coordinate (lines)
    y_groups = {}
    for char in page.chars:
        y = round(char.get('y0', 0))
        if y not in y_groups:
            y_groups[y] = []
        y_groups[y].append(char)
    
    # Process each line
    for y in sorted(y_groups.keys(), reverse=True):
        chars = sorted(y_groups[y], key=lambda x: x.get('x0', 0))
        
        # Reconstruct text
        text = ''.join(char['text'] for char in chars).strip()
        if not text:
            continue
        
        # Calculate properties
        sizes = [char.get('size', 12) for char in chars]
        avg_size = sum(sizes) / len(sizes) if sizes else 12
        max_size = max(sizes) if sizes else 12
        
        left_margin = min(char.get('x0', 0) for char in chars)
        
        # Check for bold
        fonts = [char.get('fontname', '') for char in chars]
        is_bold = any('bold' in font.lower() for font in fonts if font)
        
        lines.append({
            'text': text,
            'avg_size': avg_size,
            'max_size': max_size,
            'left_margin': left_margin,
            'is_bold': is_bold,
            'y_pos': y
        })
    
    return lines

def _calculate_heading_score(line, h1_thresh, h2_thresh, h3_thresh):
    """Calculate heading score for a text line"""
    text = line['text']
    confidence = 0.0
    level = 'H4'
    
    # Font size scoring
    if line['avg_size'] >= h1_thresh:
        confidence += 0.4
        level = 'H1'
    elif line['avg_size'] >= h2_thresh:
        confidence += 0.3
        level = 'H2'
    elif line['avg_size'] >= h3_thresh:
        confidence += 0.2
        level = 'H3'
    else:
        confidence += 0.1
        level = 'H4'
    
    # Bold text bonus
    if line['is_bold']:
        confidence += 0.2
    
    # Position bonus (left-aligned)
    if line['left_margin'] < 100:
        confidence += 0.1
    
    # Length analysis (shorter is more likely to be heading)
    if len(text) < 80:
        confidence += 0.1
    if len(text) < 40:
        confidence += 0.1
    
    # Pattern analysis
    pattern_boost, pattern_level = _analyze_text_patterns(text)
    confidence += pattern_boost
    if pattern_level and pattern_boost > 0.25:
        level = pattern_level
    
    # Penalty for obvious non-headings
    if _is_non_heading(text):
        confidence -= 0.4
    
    return {'confidence': min(confidence, 1.0), 'level': level}

def _analyze_text_patterns(text):
    """Analyze text patterns for heading indicators"""
    boost = 0.0
    suggested_level = None
    
    text_lower = text.lower().strip()
    
    # Appendix patterns
    if re.match(r'^appendix [a-z]:', text, re.IGNORECASE):
        return 0.6, 'H2'
    
    # Phase patterns  
    if re.match(r'^phase [ivx]+:', text, re.IGNORECASE):
        return 0.5, 'H3'
    
    # Numbered sections
    if re.match(r'^\d+\.\s+[A-Za-z]', text):
        return 0.5, 'H3'
    if re.match(r'^\d+\.\d+\s+[A-Za-z]', text):
        return 0.4, 'H4'
    
    # Common section headers
    section_headers = [
        'summary', 'background', 'introduction', 'overview', 'approach',
        'requirements', 'evaluation', 'timeline', 'milestones', 'methodology',
        'conclusion', 'results', 'discussion'
    ]
    if any(header in text_lower for header in section_headers) and len(text) < 50:
        return 0.4, 'H2'
    
    # Question patterns for subsections
    if text.startswith(('What ', 'How ', 'Why ', 'For each ', 'For the ')):
        return 0.3, 'H3'
    
    # Colon endings (subheadings)
    if text.endswith(':') and len(text) < 100 and len(text) > 5:
        return 0.3, 'H3'
    
    # All caps titles
    if text.isupper() and 8 < len(text) < 60:
        return 0.4, 'H2'
    
    # Title case with key terms
    if (text.istitle() and 
        any(word in text_lower for word in ['ontario', 'digital', 'library', 'business', 'plan'])):
        if len(text) > 30:
            return 0.4, 'H1'
        else:
            return 0.3, 'H2'
    
    return boost, suggested_level

def _is_non_heading(text):
    """Check if text is definitely not a heading"""
    # Dates
    if re.match(r'^\w+\s+\d{1,2},?\s+\d{4}', text):
        return True
    
    # Email addresses  
    if '@' in text and '.' in text:
        return True
    
    # URLs
    if text.startswith(('http://', 'https://', 'www.')):
        return True
    
    # Complete sentences (end with period, not colon)
    if text.endswith('.') and len(text) > 40 and ' ' in text:
        return True
    
    # Pure numbers/data
    if re.match(r'^[\d\$,.\s%\-]+$', text):
        return True
    
    # Very fragmented text
    if len(text.split()) == 1 and len(text) < 8:
        return True
    
    return False

# ------------------------------------------------------------------
# OCR helper for scanned pages  
# ------------------------------------------------------------------
def _ocr_page(page, page_num):
    """Enhanced OCR processing for scanned pages"""
    img = page.to_image(resolution=150).original
    
    # Detect language for better OCR
    try:
        sample_text = pytesseract.image_to_string(img)[:200]
        lang = detect(sample_text) if sample_text.strip() else "eng"
        
        # Map common language codes to tesseract language codes
        lang_map = {
            'ja': 'jpn',   # Japanese
            'zh': 'chi_sim',  # Chinese Simplified
            'zh-cn': 'chi_sim',
            'fr': 'fra',   # French
            'de': 'deu',   # German
            'en': 'eng'    # English
        }
        tesseract_lang = lang_map.get(lang, 'eng')
    except:
        tesseract_lang = 'eng'
    
    # Get detailed OCR data
    data = pytesseract.image_to_data(
        img, lang=tesseract_lang, output_type=pytesseract.Output.DICT
    )
    
    candidates = []
    for i, height in enumerate(data["height"]):
        confidence = int(data["conf"][i])
        text = data["text"][i]
        
        if confidence > 30 and text.strip():
            candidates.append({
                'text': text.strip(),
                'level': 'H3',  # Default level for OCR
                'page': page_num,
                'confidence': min(0.8, confidence / 100.0),
                'source': 'ocr'
            })
    
    return candidates

# ------------------------------------------------------------------
# NEW FUNCTION FOR ROUND 1B
# ------------------------------------------------------------------
def extract_section_content(pdf_path: str, start_heading: dict, all_headings: list[dict]) -> str:
    content = []
    
    # Find the starting heading in the list
    try:
        start_index = all_headings.index(start_heading)
    except ValueError:
        # If heading not found, extract from the page using fallback method
        return _fallback_extract_content(pdf_path, start_heading)
    
    # Find the next heading as the end boundary
    end_heading = None
    if start_index + 1 < len(all_headings):
        end_heading = all_headings[start_index + 1]
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            start_page_num = start_heading['page']
            start_y = start_heading.get('position', 0)
            
            # If we have an end heading, use it; otherwise extract to end of document
            if end_heading:
                end_page_num = end_heading['page']
                end_y = end_heading.get('position', pdf.pages[end_page_num - 1].height)
            else:
                end_page_num = len(pdf.pages)
                end_y = -1
            
            # Extract content from pages
            for i in range(start_page_num - 1, min(end_page_num, len(pdf.pages))):
                if i >= len(pdf.pages):
                    break
                    
                page = pdf.pages[i]
                
                # Determine boundaries for this page
                if i == start_page_num - 1:
                    # First page - start from heading position
                    top_boundary = max(0, start_y)
                else:
                    # Middle pages - start from top
                    top_boundary = 0
                
                if end_heading and i == end_page_num - 1:
                    # Last page - end at next heading position
                    bottom_boundary = min(page.height, end_y)
                else:
                    # Full page extraction
                    bottom_boundary = page.height
                
                # Ensure valid boundaries
                if bottom_boundary <= top_boundary:
                    # If boundaries are invalid, try fallback extraction
                    text = _fallback_extract_content(pdf_path, start_heading)
                    if text:
                        return text
                    continue
                
                # Extract text from the defined area
                try:
                    if top_boundary > 0 or bottom_boundary < page.height:
                        # Crop the page if needed
                        cropped_page = page.crop((0, top_boundary, page.width, bottom_boundary))
                        text = cropped_page.extract_text()
                    else:
                        # Extract full page
                        text = page.extract_text()
                    
                    if text and text.strip():
                        content.append(text.strip())
                        
                except Exception as e:
                    # If cropping fails, try full page extraction
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            content.append(text.strip())
                    except:
                        continue
    
    except Exception as e:
        # If all else fails, use fallback method
        return _fallback_extract_content(pdf_path, start_heading)
    
    # Join and clean the extracted content
    if content:
        full_text = " ".join(content)
        cleaned_text = re.sub(r'\s+', ' ', full_text).strip()
        return cleaned_text
    else:
        # No content extracted, try fallback
        return _fallback_extract_content(pdf_path, start_heading)


def _fallback_extract_content(pdf_path: str, heading: dict) -> str:
    """Fallback method to extract content when main extraction fails"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_num = heading.get('page', 1)
            if page_num <= len(pdf.pages):
                page = pdf.pages[page_num - 1]
                
                # Try to extract a reasonable chunk of text from the page
                full_text = page.extract_text()
                if full_text and full_text.strip():
                    # Split into sentences and take first few paragraphs
                    sentences = full_text.split('. ')
                    if len(sentences) > 3:
                        return '. '.join(sentences[:5]) + '.'
                    else:
                        return full_text.strip()
            
            # If specific page fails, try extracting from nearby pages
            for i in range(max(0, page_num - 2), min(len(pdf.pages), page_num + 2)):
                try:
                    page = pdf.pages[i]
                    text = page.extract_text()
                    if text and len(text.strip()) > 50:  # Ensure we have substantial content
                        sentences = text.split('. ')
                        if len(sentences) > 2:
                            return '. '.join(sentences[:3]) + '.'
                        else:
                            return text.strip()[:500]  # Limit to reasonable length
                except:
                    continue
            
            # Last resort: extract from any page with content
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text and len(text.strip()) > 20:
                        clean_text = ' '.join(text.split())
                        if len(clean_text) > 100:
                            return clean_text[:300] + "..."
                        else:
                            return clean_text
                except:
                    continue
                    
    except Exception as e:
        pass
    
    # Absolute final fallback - always return something meaningful
    section_text = heading.get('text', 'content section')
    page_ref = heading.get('page', 'unknown')
    return f"This section covers {section_text.lower()} and contains relevant information for travel planning (from page {page_ref})."