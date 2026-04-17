import re

def test_regex():
    sample_texts = [
        "Identity No. 1234567890 Student Name: Majed Al-Harbi Section: A GPA: 4.5",
        "رقم الهوية: 1234567890 اسم الطالب: ماجد الحربي الفصل: أ المعدل: 4.5",
        "اسم الطالب: محمد   رقم السجل المدني 2222222222 الفصل: ب",
        "الرقم المدني 1111111111 الاسم: خالد GPA 3.1",
        "Just a number 1234567890 on the page"
    ]
    
    id_pat = r'(?:Identity No|رقم الهوية|رقم السجل المدني|الرقم المدني)[.\s:]+(\d{8,12})'
    name_pat = r'(?:Student Name|اسم الطالب|الاسم)[.\s:]+(.+?)(?:Section|الفصل|GPA|Average|$)'
    sec_pat = r'(?:Section|الفصل)[.\s:]+(\S+)'
    
    for text in sample_texts:
        print(f"Testing: {text}")
        m_id = re.search(id_pat, text, re.IGNORECASE)
        if not m_id:
            m_id = re.search(r'\b([12]\d{9})\b', text)
            
        m_name = re.search(name_pat, text, re.IGNORECASE)
        m_sec = re.search(sec_pat, text, re.IGNORECASE)
        
        print(f"  ID: {m_id.group(1) if m_id else 'None'}")
        print(f"  Name: {m_name.group(1).strip() if m_name else 'None'}")
        print(f"  Section: {m_sec.group(1).strip() if m_sec else 'None'}")
        print("-" * 20)

if __name__ == "__main__":
    test_regex()
