from prop_hunter_bref_usage import parse_bref_usage_csv

sample = "Player,USG%,bref_id\nExample One,28.4,example01\nExample Two,17.2,example02\nUnknown,99.0,unknown\nBad,NaN,bad\n"
got = parse_bref_usage_csv(sample, {"example01": 123, "example02": 456, "bad": 789})
assert got[123]["usage_pct"] == 28.4
assert got[456]["source"] == "basketball_reference_csv"
assert len(got) == 2
assert got[123]["scope"] == "season"
assert parse_bref_usage_csv(sample, {}) == {}
try:
    parse_bref_usage_csv("Player,USG%\nX,25\n", {})
except ValueError:
    pass
else:
    raise AssertionError("missing CSV columns accepted")
try:
    parse_bref_usage_csv("Player,USG%,bref_id\nA,20,a\nB,30,b\n", {"a":123,"b":123})
except ValueError:
    pass
else:
    raise AssertionError("duplicate NBA ID accepted")
print("BREF SEASON USAGE CSV FALLBACK PASSED")
