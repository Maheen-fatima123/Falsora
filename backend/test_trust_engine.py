from modules.trust_engine import calculate_trust_score, calculate_rolling_trust

result = calculate_trust_score(forgery_score=0.9, exif_flags=["missing_gps", "modified_date"], fingerprint_match=False)
print("Test 1 (fake image):", result)
# Expect: trust_score around 8, risk_level = High-Risk

result = calculate_trust_score(forgery_score=0.1, exif_flags=[], fingerprint_match=False)
print("Test 2 (real image):", result)
# Expect: trust_score around 90, risk_level = Authentic

result = calculate_rolling_trust([0.3, 0.25, 0.28, 0.32, 0.29])
print("Test 3 (live stream):", result)
# Expect: trust_score around 29, risk_level = High-Risk