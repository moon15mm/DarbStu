with open("database.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "import_teachers_from_excel" in line:
            print(f"Line {i+1}: {line.strip()}")
