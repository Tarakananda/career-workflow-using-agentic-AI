#!/usr/bin/env python3
"""Fix the _interactive_answer method in chatbot_answerer.py"""

with open('src/chatbot_answerer.py', 'rb') as f:
    content = f.read()

# Find the malformed method definition
idx = content.find(b'                    _interactive_answer(self, question: str, chatbot_container: ElementHandle, page: Page) -> bool:')
if idx >= 0:
    # Find the end of this method (next method or end of class)
    next_method = content.find(b'\n        def ', idx + 50)
    if next_method == -1:
        next_method = content.find(b'    def ', idx + 50)
    if next_method == -1:
        next_method = len(content)
    
    # New method implementation
    new_method = b'''        def _interactive_answer(self, question: str, chatbot_container: ElementHandle, page: Page) -> bool:
        """Pause and wait for user to manually answer the question."""
        print(f"\\n  \xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90")
        print(f"  \xe2\x95\xb8  MANUAL ANSWER REQUIRED")
        self._debug(f"  Question: {question}")
        print(f"  You have 8 seconds to type your answer in the browser...")

        # Wait for user to type answer (8 seconds)
        for i in range(8, 0, -1):
            print(f"  Waiting for your input... {i}s", end="\r")
            time.sleep(1)
        print("  " + " " * 40, end="\r")

        # Try to find the answer that was entered
        answer = self._get_entered_answer(chatbot_container, page)
        if answer:
            # Save to profile Q&A for future use
            self._save_answer_to_profile(question, answer)
            print(f"  [Chatbot] Saved answer: '{answer}' for future use")
            return True

        return False
'''
        content = content[:idx] + new_method + content[idx+500:]
        with open('src/chatbot_answerer.py', 'wb') as f:
            f.write(content)
        print('Fixed _interactive_answer method')