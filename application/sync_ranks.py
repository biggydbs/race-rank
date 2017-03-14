from elo_rating import elo_match
from application import db, ROOT_DIR
from bson.objectid import ObjectId
import pymongo
import operator

# Calculate the advantage points for 1st , 2nd, 3rd, finisher and dnf riders.
def advantage_points():
	first = 28
	second = 21
	third = 14
	finisher = 7
	dnf = 2
	return {
			"first" : first,
			"second" : second,
			"third" : third,
			"finisher" : finisher,
			"dnf" : dnf
		}
		
# Function which can do everything for sync db
def revise_all_ranks():
	update_adv_point_and_final_score_to_0()
	update_elo_rating_to_1000()
	update_cgpa_ratings_to_0()
	synchronize_databases()
	update_cgpa_ratings()

def update_adv_point_and_final_score_to_0():
	results = db.results
	all_results = results.find({}, sort = [("race_date.year",1),("race_date.month",1),("race_date.date",1)])
	for cur_result in all_results:
		cur_race_name = cur_result["race_name"]
		cur_race_result = cur_result["race_result"]
		for cur_ser_num in cur_race_result:
			ser_num = "race_result.{cur_ser_num}.advantage_point".format(cur_ser_num = cur_ser_num)
			ser_num2 = "race_result.{cur_ser_num}.final_score".format(cur_ser_num = cur_ser_num)
			# Update for every rider
			results.update_one(
				{ 
					"race_name" : cur_race_name
				},
				{
					"$set" : {
						str(ser_num) : 0,
						str(ser_num2) : 0
					}
				}	
			)
	return "Updated"

def update_elo_rating_to_1000():
	users = db.users
	users.update(
			{},
			{
				"$set":{
					"elo_rating" : float(1000)
				}
			},
			multi = True
		)
	return "Updated"

def update_cgpa_ratings_to_0():
	users = db.users
	users.update(
			{},
			{
				"$set":{
					"cgpa_rating" : float(0)
				}
			},
			multi = True
		)
	return "Updated"

# Sync db---
def synchronize_databases():
	users = db.users
	results = db.results
	# get the races according to dates
	all_results = results.find({}, sort = [("race_date.year",1),("race_date.month",1),("race_date.date",1)])
	adv_pts = advantage_points()
	for cur_result in all_results:
		if cur_result["active"] == "yes" or cur_result["active"] == "Yes":
			cur_race_name = cur_result["race_name"]
			cur_race_result = cur_result["race_result"]
			cur_scores = {}
			dnf_riders = []
			cur_adv_point = {}
			tagged_riders = {}
			tagged_riders_matched = {}
			# Uodate advantage points
			for cur_ser_num in cur_race_result:
				rider_tag = cur_race_result[cur_ser_num]["rider_tag"]
				if rider_tag != "":
					total_race_time = cur_race_result[cur_ser_num]["total_race_time"]
					tagged_riders[cur_ser_num] = total_race_time
					tagged_riders_matched[cur_ser_num] = rider_tag
					try:
						cur_scores[cur_ser_num] = float(total_race_time)
						cur_adv_point[cur_ser_num] = adv_pts["finisher"]
					except:
						dnf_riders.append(cur_ser_num)
						cur_adv_point[cur_ser_num] = adv_pts["dnf"]
			cur_scores = sorted(cur_scores.items(), key=operator.itemgetter(1))
			ct = 1
			for scores in cur_scores:
				if ct > 3:
					break
				if ct == 1:
					cur_adv_point[scores[0]] = adv_pts["first"]
				elif ct == 2:
					cur_adv_point[scores[0]] = adv_pts["second"]
				elif ct == 3:
					cur_adv_point[scores[0]] = adv_pts["third"]
				else:
					break
				ct += 1
			for cur_ser_num in cur_adv_point:
				ser_num = "race_result.{cur_ser_num}.advantage_point".format(cur_ser_num = cur_ser_num)
				results.update_one(
					{ 
						"race_name" : cur_race_name
					},
					{
						"$set" : {
							str(ser_num) : cur_adv_point[cur_ser_num]
						}
					}	
				)
			# Update Final score for every rider 
			cur_race = results.find_one({"race_name":cur_race_name})
			score_dic = []
			max_total_time = float("-inf")
			min_total_time = float("inf")
			for cur_ser_num in cur_race["race_result"]:
				cur_score = {}
				cur_score[cur_ser_num] = {
					"adv_point" : cur_race["race_result"][cur_ser_num]["advantage_point"],
					"total_time" : cur_race["race_result"][cur_ser_num]["total_race_time"]
				}
				if cur_race["race_result"][cur_ser_num]["total_race_time"] != "DNF" and cur_race["race_result"][cur_ser_num]["total_race_time"] != "" and cur_race["race_result"][cur_ser_num]["total_race_time"] != "dnf":
					max_total_time = max(cur_race["race_result"][cur_ser_num]["total_race_time"], max_total_time)
					min_total_time = min(cur_race["race_result"][cur_ser_num]["total_race_time"], min_total_time)
				score_dic.append(cur_score)
			difficulty = cur_result.get("difficulty",1)
			if difficulty == 0:
				difficulty = 1	
			div_factor = 100.0 / (max_total_time - min_total_time)
			for scores in score_dic:
				adv_point = 0
				for score in scores:
					ser_num = score
					cur_serial_num = "race_result.{ser_num}.final_score".format(ser_num=ser_num) 
					cur_score = scores[score]["total_time"]
					adv_point = scores[score]["adv_point"]
				try:
					final_score = "%.3f"%((int(max_total_time) - int(cur_score)) * div_factor + adv_point )
					
					results.update_one(
						{
							"race_name" : cur_race_name
						},
						{
							"$set" : {
							str(cur_serial_num) : float(final_score) * difficulty
							}
						}
					)
				except:
					results.update_one(
						{
							"race_name": cur_race_name
						},
						{
							"$set" : {
							str(cur_serial_num) : adv_point * difficulty
							}
						}
					)
			
			difficulty = cur_result.get("difficulty",1)
			if difficulty == 0:
				difficulty = 1
			final_scores = sorted(tagged_riders.items(), key=operator.itemgetter(1))
			for diff in range(difficulty):
				# select previous elo rating
				prev_ratings = {}
				for tagged_r in tagged_riders_matched:
					rider_id = tagged_riders_matched[tagged_r]
					cur_rider_rating = users.find_one(
						{
							"_id":ObjectId(rider_id)
						},
						{
							"elo_rating" : 1
						}
					)
					prev_ratings[tagged_r] = cur_rider_rating["elo_rating"]

				ct = 0
				final_ratings = []
				# Calculate new elo rating
				final_ratings = elo_match()
				serial_num_list = []
				for final_score in final_scores:
					try:
						rating = float(prev_ratings[final_score[0]])
						ct += 1
						serial_num_list.append(final_score[0])
						final_ratings.add_rider(final_score[0],ct,rating)
					except:
						pass
				final_ratings.calculate_elo_rating()
				for i in serial_num_list:
					cur_rating = float("%.3f" % final_ratings.get_elo(i))
					rider_id = ObjectId(tagged_riders_matched[i])
					print i,cur_rating
					if rider_id != "":
						# Update the elo rating
						users.update_one(
								{
									"_id":ObjectId(rider_id)
								},
								{ 
									"$set" : 
										{
											"elo_rating": cur_rating,
										}
								}
							)

def update_cgpa_ratings():
	users= db.users
	results = db.results
	# retrieve races acc to dates 
	all_results = results.find({}, sort = [("race_date.year",1),("race_date.month",1),("race_date.date",1)])
	for cur_result in all_results:
		cur_race_name = cur_result["race_name"]
		cur_race_result = cur_result["race_result"]
		for cur_ser_num in cur_race_result:
			rider_tag = cur_race_result[cur_ser_num]["rider_tag"]
			final_score = cur_race_result[cur_ser_num]["final_score"]
			if rider_tag != "":
				# retrieve previous cgpa ratings 
				prev_cgpa = users.find_one(
						{
							"_id":ObjectId(rider_tag)
						},
						{ 
							"cgpa_rating" : 1
						}
					)
				# Update new cgpa ratings
				users.update_one(
						{
							"_id":ObjectId(rider_tag)
						},
						{ 
							"$set" : 
								{
									"cgpa_rating": prev_cgpa["cgpa_rating"] + final_score
								}
						}
					)