import os

with open('src/agents/evaluator.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''        try:
            for path in image_paths:
                if not os.path.exists(path):
                    return False, f"Image not found: {path}", {}
                    
                from PIL import Image
                img = Image.open(path)
                img.verify()
                
        except Exception as e:'''

replacement = '''        try:
            for path in image_paths:
                if not os.path.exists(path):
                    return False, f"Visual asset not found: {path}", {}
                
                # If it's a video file, just check if it has size
                if path.lower().endswith(".mp4"):
                    if os.path.getsize(path) < 1024:
                        return False, f"Video asset is suspiciously small: {path}", {}
                else:
                    # Validate image with PIL
                    from PIL import Image
                    img = Image.open(path)
                    img.verify()
        except Exception as e:'''

content = content.replace(target, replacement)

with open('src/agents/evaluator.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Evaluator successfully patched.')
