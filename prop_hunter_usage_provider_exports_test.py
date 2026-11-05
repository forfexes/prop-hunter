from prop_hunter_usage_provider_exports import parse_provider_usage_csv

sample = "provider_player_id,player_name,usage_pct\na,Test One,26.2\nb,Test Two,18.5\nc,Invalid,NaN\n"
for provider in ("nbastuffer", "databallr"):
    data = parse_provider_usage_csv(sample, provider, {"a":101,"b":102,"c":103}, "2026-27")
    assert len(data) == 2
    assert data[101]["usage_pct"] == 26.2
    assert data[101]["scope"] == "season"
    assert data[101]["source"] == provider + "_csv"
    assert parse_provider_usage_csv(sample, provider, {}, "2026-27") == {}
for provider in ("unknown", ""):
    try:
        parse_provider_usage_csv(sample, provider, {}, "2026-27")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown provider accepted")
try:
    parse_provider_usage_csv("player_name,usage_pct\nX,22\n", "nbastuffer", {}, "2026-27")
except ValueError:
    pass
else:
    raise AssertionError("unmapped schema accepted")
print("NBASTUFFER AND DATABALLR CSV ADAPTERS PASSED")
