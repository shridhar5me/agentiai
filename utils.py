import re

def sanitize_text(s):
    return " ".join(s.split())

def chunk_text(s, n=2000):
    words = s.split()
    chunks = []
    for i in range(0, len(words), n):
        chunks.append(" ".join(words[i:i+n]))
    return chunks
