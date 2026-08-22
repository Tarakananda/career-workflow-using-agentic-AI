#!/usr/bin/env python3
"""Fix the _interactive_answer method in chatbot_answerer.py"""

with open('src/chatbot_answerer.py', 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if '# Wait for user to type answer (8 seconds)' in line:
        # Replace the entire method from this point
        new_lines.extend([
            '        # Wait for user to type answer (8 seconds)\n',
            '        for i in range(8, 0, -1):\n',
            '            print(f"  Waiting for your input... {i}s", end="\\r")\n',
            '            time.sleep(1)\n',
            '        print()\n',
            '\n',
            '        # Try to find the answer that was entered\n',
            '        answer = self._get_entered_answer(chatbot_container, page)\n',
            '        if answer:\n',
            '            # Save to profile Q&A for future use\n',
            '            self._save_answer_to_profile(question, answer)\n',
            '            print(f"  [Chatbot] Saved answer: \'{answer}\' for future use")\n',
            '            return True\n',
            '\n',
            '        return False\n',
            '\n',
            '    def _get_entered_answer(self, chatbot_container: ElementHandle, page: Page) -> Optional[str]:\n'
        ])
        # Skip the old implementation until we reach _get_entered_answer
        while i < len(lines) and '_get_entered_answer' not in lines[i]:
            i += 1
        # Keep the rest of the file
        new_lines.extend(lines[i:])
        break
    new_lines.append(line)
    i += 1

with open('src/chatbot_answerer.py', 'w') as f:
    f.writelines(new_lines)
print('Fixed')