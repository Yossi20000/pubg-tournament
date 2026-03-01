@echo off
C:\Python314\python.exe -c "
import base64, sys
chunks = []
for i in range(5):
    with open(rf'C:\PUBG_Tournament\b64_{i}.txt','r') as f:
        chunks.append(f.read().strip())
b64 = ''.join(chunks)
content = base64.b64decode(b64).decode('utf-8')
with open(r'C:\PUBG_Tournament\bot_control.html','w',encoding='utf-8') as f:
    f.write(content)
print('bot_control.html written:', len(content), 'chars')
"
