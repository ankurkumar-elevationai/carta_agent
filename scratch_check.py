import json
data = json.load(open('frontend/data/business_data.json'))
count = 0
for c in data.get('investments', []):
    count += len(c.get('fmv_409a', []))
print('409a vals:', count)
sectors = [c.get('profile', {}).get('industry') for c in data.get('investments', [])]
print('sectors:', set(sectors))
