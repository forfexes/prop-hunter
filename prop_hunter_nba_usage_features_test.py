from prop_hunter_nba_usage_features import attach_nba_usage_form,load_nba_usage_form

row={"nba_player_id":123,"l5_observed":5,"usage_l5":28.3,
     "l10_observed":9,"usage_l10":29.0,
     "l15_observed":15,"usage_l15":26.1}
d={123:row}
assert attach_nba_usage_form({"points_avg":24},123,d)=={
    "points_avg":24,"nba_usage_l5":28.3,
    "nba_usage_l5_source":"nba_official_boxscore_usage_v3",
    "nba_usage_l15":26.1,
    "nba_usage_l15_source":"nba_official_boxscore_usage_v3"}
assert attach_nba_usage_form({"points_avg":24},None,d)=={"points_avg":24}
assert attach_nba_usage_form({},456,d)=={}
assert "nba_usage_l5" not in attach_nba_usage_form({},123,{123:{**row,"usage_l5":float("nan")}})
class Response:
    def __init__(self, data): self.data=data
class Query:
    def __init__(self, rows): self.rows=rows;self.lower=0;self.limit_n=1000
    def select(self,*args):return self
    def gt(self,k,v):self.lower=v;return self
    def order(self,*args):return self
    def limit(self,n):self.limit_n=n;return self
    def execute(self):return Response([r for r in self.rows if r["nba_player_id"]>self.lower][:self.limit_n])
class Client:
    def table(self,name):
        assert name=="prop_hunter_nba_usage_form"
        return Query([{"nba_player_id":123},{"nba_player_id":456}])
assert len(load_nba_usage_form(Client(),page_size=1))==2
print("NBA USAGE CANONICAL FEATURE BRIDGE PASSED")
