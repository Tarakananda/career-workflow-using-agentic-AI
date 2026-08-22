with open('src/matcher_v2.py', 'r') as f:
    content = f.read()

old = '"bash": "bash",'

new = '''"bash": "bash",
    "shell": "bash",
    "linux": "linux",
    "unix": "linux",
    "ubuntu": "linux",
    "centos": "linux",
    "rhel": "linux",
    "debian": "linux",'''

if old in content:
    content = content.replace(old, new)
    with open('src/matcher_v2.py', 'w') as f:
        f.write(content)
    print('Added linux aliases to matcher_v2.py')
else:
    print('Could not find pattern')
    idx = content.find('"bash": "bash",')
    if idx >= 0:
        print(f'Found at index {idx}')
        print(content[idx:idx+200])
