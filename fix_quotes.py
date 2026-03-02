import glob

files = glob.glob("09_OS_Integration/*.py") + glob.glob("04_Engine/daily_*.py") + glob.glob("10_Marketplace/*.py") + glob.glob("11_Sync_Handoff/*.py") + glob.glob("tests/test_phase6.py")

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
        
    content = content.replace('\\"', '"')
    
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Fixed {fpath}")
