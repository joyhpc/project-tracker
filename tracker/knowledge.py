"""知识引擎 — Markdown AST 切块 + BM25 本地检索

v4 架构核心：不用信号词，不用 LLM API，纯数学检索。
"""
import re
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import List
from pathlib import Path


@dataclass
class KnowledgeChunk:
    task_id: str
    task_name: str
    path: List[str]       # 标题层级，如 ["硬件选型", "BOM成本"]
    content: str           # 原始 markdown，保留表格和列表


def tokenize(text: str) -> List[str]:
    """混合分词：英文/数字连字 + 中文单字 + 中文 Bigram"""
    text = text.lower()
    tokens = []
    # 英文、数字、特殊符号连字（stm32, type-c, 0.1uf, i2c）
    tokens.extend(re.findall(r'[a-z0-9_.-]+', text))
    # 中文字符
    cjk = re.findall(r'[\u4e00-\u9fa5]', text)
    tokens.extend(cjk)
    # 中文 Bigram
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])
    return tokens


def parse_markdown(task_id: str, task_name: str, md_text: str) -> List[KnowledgeChunk]:
    """按标题层级切分 markdown 为知识块"""
    lines = md_text.split('\n')
    chunks = []
    current_path = []
    current_content = []
    in_code = False

    def save():
        text = '\n'.join(current_content).strip()
        if text and len(text) > 10:
            chunks.append(KnowledgeChunk(task_id, task_name, list(current_path), text))
        current_content.clear()

    for line in lines:
        if line.startswith('```'):
            in_code = not in_code
            current_content.append(line)
            continue

        if not in_code:
            m = re.match(r'^(#{1,6})\s+(.*)', line)
            if m:
                save()
                level = len(m.group(1))
                title = m.group(2).strip()
                if level <= len(current_path):
                    current_path = current_path[:level - 1]
                while len(current_path) < level - 1:
                    current_path.append("")
                current_path.append(title)
                continue

        current_content.append(line)

    save()

    # fallback：如果没有标题，按段落（双空行）切分
    if not chunks and md_text.strip():
        paragraphs = re.split(r'\n\s*\n', md_text)
        for p in paragraphs:
            p = p.strip()
            if len(p) > 10:
                chunks.append(KnowledgeChunk(task_id, task_name, [], p))

    return chunks


class BM25:
    """本地确定性 BM25 检索引擎"""

    def __init__(self, chunks: List[KnowledgeChunk], k1=1.5, b=0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.N = len(chunks)
        self.doc_freqs = []
        self.doc_lens = []
        self.idf = {}

        if self.N == 0:
            self.avgdl = 0
            return

        df = Counter()
        total_len = 0

        for chunk in chunks:
            text = f"{chunk.task_name} {' '.join(chunk.path)} {chunk.content}"
            tokens = tokenize(text)
            self.doc_lens.append(len(tokens))
            total_len += len(tokens)
            tf = Counter(tokens)
            self.doc_freqs.append(tf)
            df.update(tf.keys())

        self.avgdl = total_len / self.N
        for word, count in df.items():
            self.idf[word] = math.log(1 + (self.N - count + 0.5) / (count + 0.5))

    def search(self, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
        if self.N == 0:
            return []

        q_tokens = tokenize(query)
        scores = [0.0] * self.N

        for i in range(self.N):
            tf = self.doc_freqs[i]
            for token in q_tokens:
                if token not in self.idf or token not in tf:
                    continue
                freq = tf[token]
                num = freq * (self.k1 + 1)
                den = freq + self.k1 * (1 - self.b + self.b * self.doc_lens[i] / self.avgdl)
                scores[i] += self.idf[token] * (num / den)

        ranked = sorted(zip(scores, self.chunks), key=lambda x: x[0], reverse=True)
        return [chunk for score, chunk in ranked if score > 0.01][:top_k]


def build_knowledge_base(project, flow):
    """从项目任务构建知识库

    索引范围：
    - done 任务：note + note_file + 关联文档
    - in_progress 任务：关联文档（进行中的任务最需要上下文）
    - pending 任务：跳过（还没开始，没有有价值的信息）
    """
    repo = project.get("repo", "")
    all_chunks = []

    INDEXABLE = {"done", "in_progress"}
    for n in flow.get("nodes", []):
        if n.get("status") not in INDEXABLE:
            continue

        # 从 note 生成一个 chunk
        note = n.get("note", "")
        if note and len(note) > 5:
            all_chunks.append(KnowledgeChunk(n["id"], n["name"], ["结论"], note))

        # 从 note_file 解析
        if n.get("note_file") and repo:
            path = Path(repo) / n["note_file"]
            if path.exists():
                content = path.read_text(encoding="utf-8")
                all_chunks.extend(parse_markdown(n["id"], n["name"], content))

        # 从关联文档解析
        for doc in n.get("docs", []):
            fpath = doc.get("file", "") or doc.get("path", "")
            if fpath and repo:
                full = Path(repo) / fpath
                if full.exists():
                    content = full.read_text(encoding="utf-8")
                    all_chunks.extend(parse_markdown(n["id"], n["name"], content))

    return all_chunks


def retrieve_context(question, project, flow, current_task=None, top_k=5):
    """检索与问题最相关的知识块"""
    chunks = build_knowledge_base(project, flow)
    if not chunks:
        return []

    engine = BM25(chunks)

    # 查询扩展：问题 + 当前任务 + 依赖链任务名
    expanded = question
    if current_task:
        expanded = f"{current_task.get('name', '')} {current_task.get('note', '')} {question}"
        # 加入依赖链任务名
        for dep_id in current_task.get("depends", []):
            for n in flow.get("nodes", []):
                if n["id"] == dep_id:
                    expanded += f" {n['name']}"
                    break

    return engine.search(expanded, top_k=top_k)
