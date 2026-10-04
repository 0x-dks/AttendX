with open('templates/enroll.html', encoding='utf-8') as f:
    html = f.read()

issues = []

if 'id="studentSelect"' in html:
    issues.append('stale id="studentSelect" still present')

for tag in ['sp-search-wrap','sp-dropdown','sp-selected-chip','spInput','spDropdown',
            'spChip','renderDropdown','selectStudent','clearPicker','highlightMatch',
            'studentData','ALL_STUDENTS','openDropdown','closeDropdown']:
    if tag not in html:
        issues.append(f'MISSING element/function: {tag}')

if issues:
    for i in issues:
        print('FAIL:', i)
else:
    print('ALL CHECKS PASSED - enroll.html looks good')
