import math

#initialize the elo rider
class elo_rider:
    name      = ""
    place     = 0
    elo_pre    = 0
    elo_post   = 0
    elo_change = 0
    
# calculate elo rating
class elo_match:
    riders = []
    def add_rider(self, name, place, elo):
        rider = elo_rider()
        rider.name    = name
        rider.place   = place
        rider.elo_pre  = elo
        self.riders.append(rider)
        
    def get_elo(self, name):
        for p in self.riders:
            if p.name == name:
                return p.elo_post
        return 1000

    def get_elo_change(self, name):
        for p in self.riders:
            if p.name == name:
                return p.elo_change
        return 0
 
    def calculate_elo_rating(self):
        n = len(self.riders)
        K = (n*1.0) / (n - 1)
        for i in range(n):
            cur_place = self.riders[i].place
            cur_elo   = self.riders[i].elo_pre  
            for j in range(n):
                if i != j:
                    opponent_place = self.riders[j].place
                    opponent_elo   = self.riders[j].elo_pre 
                    # calculate who is winning and assign points 
                    if cur_place < opponent_place:
                        S = 1.0
                    elif cur_place == opponent_place:
                        S = 0.5
                    else:
                        S = 0.0
                    # apply the formula to calculate Elo
                    EA = 1 / (1.0 + math.pow(10.0, (float(opponent_elo) - float(cur_elo)) / 400.0))
                    # Calculate Elo change
                    self.riders[i].elo_change += (K * (S - EA))
            # Final Elo for a rider
            self.riders[i].elo_post = float(self.riders[i].elo_pre) + float(self.riders[i].elo_change)