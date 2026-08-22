#!/usr/bin/env python3
"""Fix the _interactive_answer method in chatbot_answerer.py"""

with open('src/chatbot_answerer.py', 'r') as f:
    content = f.read()

# Find the malformed line
idx = content.find('            print(f"  Waiting for your input... {i}s", end="\n')
if idx >= 0:
    # Fix the line
    old = '            print(f"  Waiting for your input... {i}s", end="\n'
    new = '            print(f"  Waiting for your input... {i}s", end="\\r")\n'
    content = content.replace(old, new, 1)
    
    with open('src/chatbot_answerer.py', 'w') as f:
        f.write(content)
    print('Fixed line 179')
else:
    print('Line not found')