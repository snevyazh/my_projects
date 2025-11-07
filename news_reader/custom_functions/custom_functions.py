import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def count_tokens(text):
    return len(text.split()) * 4 / 3