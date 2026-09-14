"""
Offline arXiv paper discovery: fuzzy, repeatable, no API dependency.
Parses markdown/HTML saved search files, finds papers not in papers.yaml.
Can also fetch fresh search results (fallback to cache).

Usage:
  python scripts/search_arxiv_offline.py --help
  python scripts/search_arxiv_offline.py --fetch    # fetch + find new papers
  python scripts/search_arxiv_offline.py --save     # also save to papers.yaml
"""

import re, sys, os, json, hashlib
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime

ROOT = Path(__file__).parent.parent
PAPERS_FILE = ROOT / "papers.yaml"
CACHE_DIR = ROOT / ".search_cache"
CACHE_DIR.mkdir(exist_ok=True)

# ======== Try optional deps ========
try:
    import yaml
except ImportError:
    yaml = None
try:
    import requests
except ImportError:
    requests = None

# ======== Fuzzy matching ========
def title_similarity(a, b):
    a = re.sub(r'[^\w\s]', '', a.lower()).strip()
    b = re.sub(r'[^\w\s]', '', b.lower()).strip()
    return SequenceMatcher(None, a, b).ratio()

def is_duplicate(title, papers, threshold=0.70):
    for p in papers:
        if title_similarity(title, p['title']) >= threshold:
            return True
    return False

# ======== Paper loading/saving ========
def load_papers():
    if yaml is None:
        print("ERROR: PyYAML required")
        sys.exit(1)
    with open(PAPERS_FILE) as f:
        return yaml.safe_load(f)['papers']

def save_papers(papers):
    if yaml is None:
        return
    with open(PAPERS_FILE, 'w') as f:
        yaml.dump({'papers': papers}, f, default_flow_style=None,
                  sort_keys=False, allow_unicode=True, width=120)

# ======== Fetch + Cache ========
def fetch_search(query, start=0):
    """Fetch arXiv search HTML, return raw text."""
    key = hashlib.md5(f"arxiv:{query}:{start}".encode()).hexdigest()
    cache = CACHE_DIR / f"{key}.html"
    
    if cache.exists():
        return cache.read_text(encoding='utf-8', errors='replace')
    
    if requests is None:
        print("  [SKIP] requests not available, no cached data")
        return None
    
    url = f"https://arxiv.org/search/?query={requests.utils.quote(query)}&searchtype=all&start={start}"
    try:
        r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        cache.write_text(r.text, encoding='utf-8')
        return r.text
    except Exception as e:
        print(f"  [FAIL] {e}")
        return None

# ======== Parse arXiv search HTML ========
def parse_html(html):
    """Parse arXiv search results HTML into paper dicts."""
    papers = []
    # Each result: <a href="/abs/ID"> followed by title and abstract
    blocks = re.split(r'arXiv:\d{4}\.\d{4,5}', html)
    
    # Extract all arXiv IDs with their context
    # Pattern: arXiv:ID in a link
    pattern = r'arxiv\.org/abs/(\d{4}\.\d{4,5})'
    ids = re.findall(pattern, html)
    
    # Split by result boundaries (each result has a listing-title div or similar)
    # arXiv search results are in <li class="arxiv-result"> blocks
    result_blocks = re.split(r'<li class="arxiv-result"', html)[1:]
    
    for block in result_blocks:
        # arXiv ID
        aid_match = re.search(r'arxiv\.org/abs/(\d{4}\.\d{4,5})', block)
        if not aid_match:
            continue
        arxiv_id = aid_match.group(1)
        
        # Title - between <p class="title"> and </p>
        title = ""
        t = re.search(r'<p class="title[^"]*"[^>]*>\s*(.*?)\s*</p>', block, re.DOTALL)
        if t:
            title = re.sub(r'<[^>]+>', '', t.group(1)).strip()
        
        # Authors
        authors = []
        a = re.search(r'<p class="authors[^"]*"[^>]*>\s*(.*?)\s*</p>', block, re.DOTALL)
        if a:
            authors_text = re.sub(r'<[^>]+>', '', a.group(1))
            authors_text = re.sub(r'\s+', ' ', authors_text).strip()
            # Remove "Authors:" prefix
            authors_text = re.sub(r'^Authors:\s*', '', authors_text)
            authors = [x.strip() for x in authors_text.split(',') if x.strip() and 'et al' not in x]
        
        # Abstract
        abstract = ""
        abs_match = re.search(r'<span class="abstract-short[^"]*"[^>]*>\s*(.*?)\s*</span>', block, re.DOTALL)
        if abs_match:
            abstract = re.sub(r'<[^>]+>', '', abs_match.group(1)).strip()
            abstract = re.sub(r'\s+', ' ', abstract)
            abstract = re.sub(r'^▽\s*', '', abstract)
        
        # Date - "Submitted DD Month, YYYY" or similar
        date = ""
        d = re.search(r'Submitted\s+\d+\s+(\w+)\s*,?\s*(\d{4})', block)
        if d:
            month_map = dict(jan='01',feb='02',mar='03',apr='04',may='05',jun='06',
                           jul='07',aug='08',sep='09',oct='10',nov='11',dec='12')
            for k, v in month_map.items():
                if d.group(1).lower().startswith(k):
                    date = f"{d.group(2)}-{v}"
                    break
        
        # Subjects/categories
        subjects = ""
        s = re.search(r'Subjects:\s*(.*?)(?:</p>|\n)', block, re.DOTALL)
        if s:
            subjects = re.sub(r'<[^>]+>', '', s.group(1)).strip()
        
        if title:
            papers.append({
                'arxiv_id': arxiv_id,
                'title': title,
                'authors': authors[:15],
                'abstract': abstract,
                'date': date,
                'subjects': subjects,
                'url': f'https://arxiv.org/abs/{arxiv_id}',
            })
    
    return papers

# ======== Parse markdown (webfetch output) ========
def parse_markdown(text):
    """Parse markdown-formatted search results (from webfetch tool)."""
    papers = []
    
    # Find all arXiv IDs
    ids = re.findall(r'\[?(\d{4}\.\d{4,5})\]?', text)
    
    # Split by ID boundaries
    blocks = re.split(r'\n\n(?=\d+\.\s*\[?arXiv:)', text)
    if len(blocks) == 1:
        blocks = re.split(r'\n(?=\d+\.\s*)', text)
    
    for block in blocks:
        aid_match = re.search(r'(\d{4}\.\d{4,5})', block)
        if not aid_match:
            continue
        arxiv_id = aid_match.group(1)
        
        # Title - first line after the ID
        lines = block.strip().split('\n')
        title = ""
        for line in lines:
            line = line.strip()
            if arxiv_id in line and ('[' in line or 'arXiv' in line):
                # Get the text after the ID
                parts = re.split(r'\]?\)?\s*', line)
                for p in parts:
                    p = p.strip().strip('[]')
                    if p.startswith('http'):
                        continue
                    if len(p) > 30 and not p.startswith(arxiv_id):
                        title = p
                        break
            elif not title and len(line) > 30 and 'Abstract' not in line and 'Authors' not in line and 'Submitted' not in line:
                # Maybe it's a continuation
                if not line.startswith('cs.') and not line.startswith('quant'):
                    title = line
        
        # Try alternative: title is often in bold/markdown link
        if not title:
            tm = re.search(r'\[([^\]]{20,})\]\(https://arxiv.org/abs/' + re.escape(arxiv_id), block)
            if tm:
                title = tm.group(1)
        
        # Authors
        authors = []
        am = re.search(r'Authors:\s*\[?([^\]]*)\]?', block)
        if am:
            authors_text = am.group(1).strip()
            authors = [a.strip().strip('(').strip(')') for a in authors_text.split(',') if a.strip()]
            # Clean up parenthetical affiliations
            authors = [re.sub(r'\s*\(.*?\)\s*', '', a).strip() for a in authors]
        
        # Abstract
        abstract = ""
        abs_match = re.search(r'Abstract:\s*(.*?)(?:△ Less|$)', block, re.DOTALL)
        if abs_match:
            abstract = re.sub(r'▽\s*', '', abs_match.group(1)).strip()
        
        # Date
        date = ""
        d = re.search(r'Submitted\s+\d+\s+(\w+)\s*,?\s*(\d{4})', block)
        if d:
            month_map = dict(jan='01',feb='02',mar='03',apr='04',may='05',jun='06',
                           jul='07',aug='08',sep='09',oct='10',nov='11',dec='12')
            for k, v in month_map.items():
                if d.group(1).lower().startswith(k):
                    date = f"{d.group(2)}-{v}"
                    break
        
        if title:
            papers.append({
                'arxiv_id': arxiv_id,
                'title': title.strip().strip('[]'),
                'authors': authors[:15],
                'abstract': abstract,
                'date': date,
                'url': f'https://arxiv.org/abs/{arxiv_id}',
            })
    
    return papers

# ======== Classification ========
def classify(paper):
    text = f"{paper['title']} {paper['abstract']}".lower()
    
    # Category: experiential vs working vs factual
    exp_score = sum(text.count(w) for w in ['episodic', 'experiential', 'experience', 'narrative',
       'event', 'conversation', 'dialogue', 'interaction', 'reflect', 'reflection',
       'personal', 'user profile', 'preference', 'lifelong', 'stream'])
    work_score = sum(text.count(w) for w in ['working memory', 'short-term', 'context',
       'cache', 'kv', 'buffer', 'attention', 'online', 'real-time', 'realtime',
       'inference', 'latency', 'bandwidth', 'runtime', 'concurrent'])
    
    if work_score >= exp_score:
        cat = 'working'
    elif exp_score > 0:
        cat = 'experiential'
    else:
        cat = 'factual'
    
    # Subcategory
    param_score = sum(text.count(w) for w in ['parametric', 'fine-tun', 'finetun', 
        'gradient', 'weight', 'learning', 'rl', 'reinforcement', 'policy'])
    latent_score = sum(text.count(w) for w in ['latent', 'embedding', 'vector', 
        'graph', 'knowledge graph', 'neural', 'representation', 'implicit'])
    
    if param_score >= 2 and param_score > latent_score:
        sub = 'parametric'
    elif latent_score >= 2:
        sub = 'latent'
    else:
        sub = 'token-level'
    
    return cat, sub

def auto_tags(paper):
    text = f"{paper['title']} {paper['abstract']}".lower()
    tags = []
    keywords = [
        ('benchmark', ['benchmark', 'evaluation', 'leaderboard']),
        ('security', ['attack', 'adversarial', 'security', 'poison', 'injection']),
        ('forgetting', ['forget', 'compaction', 'eviction', 'prune']),
        ('multimodal', ['multimodal', 'vision', 'video', 'audio']),
        ('retrieval', ['retrieval', 'rag', 'search', 'index']),
        ('rl', ['reinforcement learning', 'policy', 'reward']),
    ]
    for tag, kw in keywords:
        if any(k in text for k in kw):
            tags.append(tag)
    return tags[:4]

# ======== Main ========
def search(queries, pages=2, force_fetch=False, verbose=True):
    papers = load_papers()
    existing_urls = {p['url'] for p in papers}
    new_papers = []
    
    for query in queries:
        if verbose: print(f"\n=== Query: '{query}' ===")
        for page in range(pages):
            start = page * 50
            html = fetch_search(query, start)
            if not html:
                if verbose: print(f"  Page {page+1}: no data")
                continue
            
            results = parse_html(html)
            if not results and html.strip().startswith('#'):
                results = parse_markdown(html)
            
            if verbose: print(f"  Page {page+1} ({start}+): {len(results)} results")
            
            for r in results:
                title = r['title'].strip()
                if not title or len(title) < 10:
                    continue
                if r['url'] in existing_urls:
                    continue
                if is_duplicate(title, papers):
                    continue
                
                cat, sub = classify(r)
                tags = auto_tags(r)
                
                entry = dict(
                    title=title,
                    date=r['date'] or '2026-07',
                    url=r['url'],
                    category=cat,
                    subcategory=sub,
                    authors=r['authors'][:15],
                    venue='', code_url='', project_url='',
                    abstract=r['abstract'],
                    tags=tags,
                )
                
                title_lower = title.lower()
                if any(k in title_lower for k in 
                    ['memory', 'forget', 'remember', 'recall', 'retrieval',
                     'context', 'experience', 'episodic', 'knowledge graph',
                     'cognitive', 'skill', 'trace', 'event', 'narrative']):
                    new_papers.append(entry)
                    papers.append(entry)
                    existing_urls.add(r['url'])
                    if verbose: print(f"  + [{cat}/{sub}] {title[:70]}")
    
    if verbose: print(f"\n=== {len(new_papers)} new papers found ===")
    return new_papers, papers

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--fetch', action='store_true', help='Fetch from arXiv')
    ap.add_argument('--save', action='store_true', help='Save to papers.yaml')
    try:
        import research_config as rc
        cfg = rc.load_config()
        default_q = [q.replace('cat:cs.AI AND abs:', '').replace('cat:cs.CL AND abs:', '').replace('"', '').strip() for q in cfg.get('arxiv_queries', [])]
        default_q = [q for q in default_q if q]
    except Exception:
        default_q = ['your topic', '"your topic" agent']
    ap.add_argument('--queries', nargs='+', default=default_q or ['your topic'])
    ap.add_argument('--pages', type=int, default=3)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    
    new, all_p = search(args.queries, pages=args.pages, force_fetch=args.force or args.fetch)
    
    if new and args.save:
        save_papers(all_p)
        print(f"Saved {len(all_p)} papers to papers.yaml")
    else:
        print(f"\nTo save, rerun with --save")
        for p in new:
            print(f"  {p['url']}  [{p['category']}/{p['subcategory']}]  {p['title'][:60]}")
