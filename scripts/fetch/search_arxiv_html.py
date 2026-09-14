"""
Offline arXiv paper search: fuzzy, repeatable, no API.
Downloads arXiv HTML search pages, parses them, and finds new papers
not already in papers.yaml using fuzzy title matching.
"""

import re
import os
import sys
import yaml
import json
import hashlib
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote_plus

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    requests = None

CACHE_DIR = Path(__file__).parent.parent / ".search_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Load existing papers
PAPERS_PATH = Path(__file__).parent.parent / "papers.yaml"

def load_papers():
    with open(PAPERS_PATH) as f:
        data = yaml.safe_load(f)
    return data['papers']

def save_papers(papers):
    with open(PAPERS_PATH, 'w') as f:
        yaml.dump({'papers': papers}, f, default_flow_style=None, sort_keys=False, allow_unicode=True, width=120)

def title_similarity(a, b):
    """Fuzzy title match score (0-1), ignoring case/punctuation."""
    a = re.sub(r'[^\w\s]', '', a.lower())
    b = re.sub(r'[^\w\s]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()

def is_duplicate(title, papers, threshold=0.75):
    """Check if a paper with similar title already exists."""
    for p in papers:
        if title_similarity(title, p['title']) >= threshold:
            return True
    return False

def fetch_search_html(query, start=0, max_results=50, force=False):
    """Download arXiv search HTML. Returns HTML string."""
    cache_key = hashlib.md5(f"{query}_{start}_{max_results}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"search_{cache_key}.html"
    
    if cache_file.exists() and not force:
        return cache_file.read_text(encoding='utf-8')
    
    if requests is None:
        print("WARNING: requests not available, using cached files only")
        return None
    
    url = f"https://arxiv.org/search/?query={quote_plus(query)}&searchtype=all&start={start}"
    try:
        resp = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        cache_file.write_text(resp.text, encoding='utf-8')
        return resp.text
    except Exception as e:
        print(f"  Fetch failed: {e}")
        return None

def parse_arxiv_search(html):
    """Parse arXiv search HTML, extract paper metadata."""
    papers = []
    
    # Find result blocks - each result is between <a> with arXiv ID and next such link
    # Use regex patterns for arXiv IDs in results
    arxiv_ids = re.findall(r'arxiv\.org/abs/(\d{4}\.\d{4,5})', html)
    
    # Find title blocks - typically in <p class="title"> or similar
    # arXiv search HTML format: title is in <a> with arXiv ID, followed by </a>\n\n<title>
    # Extract blocks per result
    results_raw = html.split('<a href="/abs/')
    
    for i, block in enumerate(results_raw[1:], 1):
        aid_match = re.match(r'(\d{4}\.\d{4,5})', block)
        if not aid_match:
            continue
        arxiv_id = aid_match.group(1)
        
        # Extract title - between "Title:" and next section marker
        title = ""
        title_match = re.search(r'Title:\s*(.*?)(?:\n|$)', block)
        if title_match:
            title = title_match.group(1).strip()
        else:
            # Try alternative pattern
            title_match = re.search(r'class="title-text">([^<]+)', block)
            if title_match:
                title = title_match.group(1).strip()
            else:
                # Try extracting from the listing-title link
                title_match = re.search(r'<a[^>]*>([^<]+)</a>\s*</div>\s*<div', block)
                if title_match:
                    title = title_match.group(1).strip()
        
        # Extract authors
        authors = []
        authors_match = re.search(r'Authors:(.*?)(?:\n\s*\n|$)', block, re.DOTALL)
        if authors_match:
            authors_text = authors_match.group(1).strip()
            # Clean up author names
            authors = [a.strip().strip(',').strip() for a in re.split(r',\s*(?![^(]*\))', authors_text) if a.strip()]
        
        # Extract abstract
        abstract = ""
        abstract_match = re.search(r'Abstract:\s*(.*?)(?:\n\s*\n|$)', block, re.DOTALL)
        if abstract_match:
            abstract = abstract_match.group(1).strip()
        
        # Extract date from "Submitted" or similar line
        date = ""
        date_match = re.search(r'Submitted\s+\d+\s+(\w+)\s*,?\s*(\d{4})', block)
        if date_match:
            month_map = {
                'january': '01', 'february': '02', 'march': '03', 'april': '04',
                'may': '05', 'june': '06', 'july': '07', 'august': '08',
                'september': '09', 'october': '10', 'november': '11', 'december': '12'
            }
            month = month_map.get(date_match.group(1).lower(), '00')
            year = date_match.group(2)
            date = f"{year}-{month}"
        
        # Extract from "originally announced" or similar
        if not date:
            date_match = re.search(r'originally announced\s+(\w+)\s+(\d{4})', block, re.IGNORECASE)
            if date_match:
                month_map = {
                    'january': '01', 'february': '02', 'march': '03', 'april': '04',
                    'may': '05', 'june': '06', 'july': '07', 'august': '08',
                    'september': '09', 'october': '10', 'november': '11', 'december': '12'
                }
                month = month_map.get(date_match.group(1).lower(), '00')
                year = date_match.group(2)
                date = f"{year}-{month}"
        
        # Extract categories
        categories = []
        cat_match = re.search(r'Subjects:\s*(.*?)(?:\n\s*\n|$)', block, re.DOTALL)
        if cat_match:
            cats_text = cat_match.group(1).strip()
            categories = re.findall(r'([a-z\-]+(?:\.[A-Za-z]+)+)', cats_text)
        
        papers.append({
            'arxiv_id': arxiv_id,
            'title': title,
            'authors': authors,
            'abstract': abstract,
            'date': date,
            'categories': categories,
            'url': f'https://arxiv.org/abs/{arxiv_id}'
        })
    
    return papers

def classify_paper(paper):
    """Heuristic classification: category/subcategory based on title+abstract."""
    text = f"{paper['title']} {paper['abstract']}".lower()
    
    # Category
    is_experiential = any(w in text for w in ['episodic', 'experiential', 'experience', 'narrative', 
                                               'event', 'conversation', 'dialogue', 'interaction',
                                               'reflect', 'reflection'])
    is_working = any(w in text for w in ['working memory', 'short-term', 'context management',
                                          'cache', 'kv cache', 'buffer', 'attention',
                                          'online', 'realtime', 'real-time', 'inference'])
    
    if is_working and not is_experiential:
        cat = 'working'
    elif is_experiential:
        cat = 'experiential'
    else:
        cat = 'factual'
    
    # Subcategory
    is_parametric = any(w in text for w in ['parametric', 'parameter', 'weight', 'model update',
                                             'fine-tun', 'finetun', 'gradient', 'learning'])
    is_latent = any(w in text for w in ['latent', 'embedding', 'vector', 'graph', 'knowledge graph',
                                         'latent representation', 'implicit'])
    is_token = any(w in text for w in ['token', 'text', 'retrieval', 'store', 'database',
                                        'key-value', 'symbolic', 'explicit'])
    
    if is_parametric and not is_latent and not is_token:
        sub = 'parametric'
    elif is_latent and not is_token:
        sub = 'latent'
    else:
        sub = 'token-level'
    
    return cat, sub

def auto_tag(paper):
    """Generate tags from title + categories."""
    text = f"{paper['title']} {paper['abstract']}".lower()
    tags = []
    
    keyword_map = {
        'benchmark': ['benchmark', 'evaluation', 'leaderboard'],
        'security': ['attack', 'adversarial', 'security', 'poison', 'injection', 'vulnerability'],
        'forgetting': ['forget', 'compaction', 'eviction', 'compression'],
        'multimodal': ['multimodal', 'vision', 'video', 'audio', 'visual'],
        'long-term memory': ['long-term', 'ltm', 'persistent'],
        'working memory': ['working memory', 'short-term', 'context'],
        'survey': ['survey', 'review', 'taxonomy'],
        'rl': ['reinforcement learning', 'rl', 'policy', 'reward'],
        'tool use': ['tool', 'mcp', 'function calling'],
    }
    
    for tag, keywords in keyword_map.items():
        if any(k in text for k in keywords):
            tags.append(tag)
    
    return tags[:6]  # max 6 tags

def search_papers(queries, max_per_query=50, pages=2, force_fetch=False):
    """Main search function: runs queries, finds new papers."""
    existing = load_papers()
    existing_urls = {p['url'] for p in existing}
    existing_titles = {p['title'] for p in existing}
    
    new_papers = []
    
    for query in queries:
        print(f"\n=== Searching: '{query}' ===")
        for page in range(pages):
            start = page * 50
            print(f"  Page {page+1} (start={start})...")
            html = fetch_search_html(query, start=start, max_results=50, force=force_fetch)
            if not html:
                print(f"  No HTML (cached or fetch failed)")
                continue
            
            results = parse_arxiv_search(html)
            print(f"  Found {len(results)} results on page")
            
            for r in results:
                if not r['title']:
                    continue
                url = r['url']
                if url in existing_urls:
                    continue
                if is_duplicate(r['title'], existing):
                    print(f"    DUPLICATE (similar title): {r['title'][:60]}...")
                    continue
                
                cat, sub = classify_paper(r)
                tags = auto_tag(r)
                
                new_entry = {
                    'title': r['title'],
                    'date': r['date'] or '2026-07',
                    'url': url,
                    'category': cat,
                    'subcategory': sub,
                    'authors': r['authors'][:10],
                    'venue': '',
                    'code_url': '',
                    'project_url': '',
                    'abstract': r['abstract'],
                    'tags': tags + [f'auto-{cat}', f'auto-{sub}'],
                }
                
                # Check if truly relevant (contains memory keywords in title)
                title_lower = r['title'].lower()
                relevance_keywords = ['memory', 'forget', 'remember', 'recall', 'retrieval', 
                                       'context', 'experience', 'episodic', 'knowledge graph']
                is_relevant = any(k in title_lower for k in relevance_keywords)
                
                if is_relevant:
                    new_papers.append(new_entry)
                    existing.append(new_entry)
                    existing_urls.add(url)
                    print(f"    NEW: [{cat}/{sub}] {r['title'][:70]}")
    
    print(f"\n=== Summary: {len(new_papers)} new papers found ===")
    return new_papers

def deduplicate_papers(papers):
    """Remove true duplicates (same URL)."""
    seen = set()
    unique = []
    for p in papers:
        url = p['url']
        if url not in seen:
            seen.add(url)
            unique.append(p)
    return unique

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Search arXiv for agent memory papers')
    try:
        import research_config as rc
        cfg = rc.load_config()
        default_q = [q.replace('cat:cs.AI AND abs:', '').replace('cat:cs.CL AND abs:', '').replace('"', '').strip() for q in cfg.get('arxiv_queries', [])]
        default_q = [q for q in default_q if q]
    except Exception:
        default_q = ['your topic', '"your topic" agent']
    parser.add_argument('--queries', nargs='+', default=default_q or ['your topic'], help='Search queries')
    parser.add_argument('--pages', type=int, default=2, help='Pages per query')
    parser.add_argument('--max-per-query', type=int, default=50, help='Results per page')
    parser.add_argument('--force', action='store_true', help='Force re-fetch')
    parser.add_argument('--save', action='store_true', help='Save new papers to yaml')
    parser.add_argument('--dry-run', action='store_true', help='Dont modify papers.yaml')
    
    args = parser.parse_args()
    
    new = search_papers(args.queries, pages=args.pages, force_fetch=args.force)
    
    if new and args.save and not args.dry_run:
        papers = load_papers()
        papers.extend(new)
        papers = deduplicate_papers(papers)
        save_papers(papers)
        print(f"Saved {len(papers)} total papers to {PAPERS_PATH}")
    elif new and not args.save:
        print("Use --save to persist changes, or --dry-run to skip")
    else:
        print("No new papers found, or --dry-run enabled")
