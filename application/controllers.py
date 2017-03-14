from flask import Blueprint, jsonify, Markup, Flask, render_template, send_from_directory, url_for, session, request, flash, g, redirect
from flask_oauth import OAuth
from flask import session
from decorators import login_required
from werkzeug import secure_filename
from pymongo import MongoClient
import pymongo
from utils import csv_to_json, store_all_predefined_users, read_xlsx, get_size, validate_name, validate_name_prefix, print_html, calculate_age, update_cgpa_ratings_with_name, update_advantage_points, check_admin
from sync_ranks import revise_all_ranks
from application import app, db, oauth, ROOT_DIR
import os
import magic
from random import randint
import datetime
from bson.objectid import ObjectId
import json
from elo_rating import elo_match
import operator
from views import calculate_races_messages

appli = Blueprint('controllers', __name__)

# Update ranks for a single race - race_name is entered as an argument and ranks are updated
@appli.route("/update_rankings",methods=["GET","POST"])
@login_required
def update_race_rankings():
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	check = check_admin(session["email"])
	Email = ""
	profile_pic = ""
	facebook_name = ""
	logged_in = False
	if "email" in session:
		logged_in = True
		Email = session["email"]
	if "profile_pic" in session:
		profile_pic = session["profile_pic"]
	if "facebook_name" in session:
		facebook_name = session["facebook_name"]
	try:
		user = users.find_one({"Email":session["email"]})
		get_image = user.get("image",None)
		session["facebook_name"] = user.get("facebook_name","")
		if get_image != None:
			session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
			var = session["profile_pic"]
			if "?" in var : 
				var = var.split("?")[0]
			var = ROOT_DIR + "/" + var
			(width, height) = get_size(var)
		else:
			(width, height) = (0,100)
	except:
		(width, height) = (0,100)
	get_html = print_html(profile_pic,facebook_name,height,Email)
	if check == True:
		results = db.results
		users = db.users
		race_name = request.args.get("race_name","")
		if race_name != "":
			result = results.find_one({"race_name":race_name})
			if result != None and result["active"] != "no" and result["active"] != "no":
				update_advantage_points(race_name)
				# Update the final score for the race
				difficulty = result.get("difficulty",1)
				if difficulty == 0:
					difficulty = 1
				for diff in range(difficulty):
					score_dic = []
					max_total_time = float("-inf")
					min_total_time = float("inf")
					prev_ratings = {}
					for ser_num in result["race_result"]:
						cur_score = {}
						cur_score[ser_num] = {
							"adv_point" : result["race_result"][ser_num]["advantage_point"],
							"total_time" : result["race_result"][ser_num]["total_race_time"],
						}
						rider_tag = result["race_result"][ser_num]["rider_tag"]
						if rider_tag != "":
							user = users.find_one({"_id":ObjectId(rider_tag)})
							try:
								prev_ratings[ser_num] = user["elo_rating"]
							except:
								pass
						if result["race_result"][ser_num]["total_race_time"] != "DNF" and result["race_result"][ser_num]["total_race_time"] != "" and result["race_result"][ser_num]["total_race_time"] != "dnf":
							max_total_time = max(result["race_result"][ser_num]["total_race_time"], max_total_time)
							min_total_time = min(result["race_result"][ser_num]["total_race_time"], min_total_time)
						score_dic.append(cur_score)
					final_scores = {}
					div_factor = 100.0 / (max_total_time - min_total_time)
					dnf_riders= [] 
					for scores in score_dic:
						adv_point = 0
						for score in scores:
							ser_num = score
							cur_serial_num = "race_result.{ser_num}.final_score".format(ser_num=ser_num) 
							cur_score = scores[score]["total_time"]
							adv_point = scores[score]["adv_point"]
						try:
							final_scores[ser_num] = "%.3f"%((int(max_total_time) - int(cur_score)) * div_factor + adv_point )
							results.update_one(
								{
									"race_name":race_name
								},
								{
									"$set" : {
									str(cur_serial_num) : float(final_scores[ser_num])
									}
								}
							)
						except:
							dnf_riders.append(ser_num)
							results.update_one(
								{
									"race_name":race_name
								},
								{
									"$set" : {
									str(cur_serial_num) : adv_point
									}
								}
							)
					final_scores = sorted(final_scores.items(), key=operator.itemgetter(1))
					ct = 0
					# Calculate the elo rating for every rider
					final_ratings = elo_match()
					ser_num_list = []
					for i in final_scores:
						try:
							rating = float(prev_ratings[i[0]])
							ser_num_list.append(i[0])
							ct += 1
							final_ratings.add_rider(i[0], ct, rating)
						except:
							pass
					final_ratings.calculate_elo_rating()
					#update elo_rating for every rider
					for i in ser_num_list:
						cur_rating = float("%.3f" % final_ratings.get_elo(i))
						rider_tag = result["race_result"][i]["rider_tag"]
						if rider_tag != "":
							users.update_one(
									{
										"_id":ObjectId(rider_tag)
									},
									{ 
										"$set" : 
											{
												"elo_rating": cur_rating,
											}
									}
							)
				# Update CGPA rating for every rider
				update_cgpa_ratings_with_name(race_name)

				return render_template(
					"update_rank.html",
					get_html = Markup(get_html),
					logged_in = logged_in,
					profile_pic = profile_pic, 
					facebook_name = facebook_name, 
					email = Email, 
					all_races = all_races,
					len_all_races = len_all_races,
					all_messages = all_messages,
					len_all_messages = len_all_messages,
					race_name = race_name,
					)
			else:
				return render_template(
					"error.html",
					error = "No Race Found , pass race name as argument -- /update_rankings?race_name={name of existing race}",
					get_html = Markup(get_html),
					logged_in = logged_in,
					profile_pic = profile_pic, 
					facebook_name = facebook_name, 
					email = Email, 
					all_races = all_races,
					len_all_races = len_all_races,
					all_messages = all_messages,
					len_all_messages = len_all_messages,
				)
		else:
			return render_template(
				"error.html",
				error = "No Race Found , pass race name as argument -- /update_rankings?race_name={name of existing race}",
				get_html = Markup(get_html),
		    	profile_pic = profile_pic, 
				facebook_name = facebook_name, 
				logged_in = logged_in,
				email = Email, 
				all_races = all_races,
				len_all_races = len_all_races,
				all_messages = all_messages,
				len_all_messages = len_all_messages,
			)
	else:
		return render_template(
			"error.html",
			error = "You Are Not Admin",
			get_html = Markup(get_html),
	    	profile_pic = profile_pic, 
			facebook_name = facebook_name, 
			logged_in = logged_in,
			email = Email, 
			all_races = all_races,
			len_all_races = len_all_races,
			all_messages = all_messages,
			len_all_messages = len_all_messages,
			)


@appli.route("/rankings",methods=["GET","POST"])
def rankings():
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	users = db.users
	Email = ""
	profile_pic = ""
	facebook_name = ""
	logged_in = False
	if "email" in session:
		Email = session["email"]
		logged_in = True
	if "profile_pic" in session:
		profile_pic = session["profile_pic"]
	if "facebook_name" in session:
		facebook_name = session["facebook_name"]
	try:
		user = users.find_one({"Email":session["email"]})
		get_image = user.get("image",None)
		session["facebook_name"] = user.get("facebook_name","")
		if get_image != None:
			session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
			var = session["profile_pic"]
			if "?" in var : 
				var = var.split("?")[0]
			var = ROOT_DIR + "/" + var
			(width, height) = get_size(var)
		else:
			(width, height) = (0,100)
	except:
		(width, height) = (0,100)
	get_html = print_html(profile_pic,facebook_name,height,Email)
	# Retrieve the sorted data to calculate ranks
	full_data = users.find({}, {"Name":1, "DOB":1, "elo_rating":1, "cgpa_rating":1}).sort("elo_rating",pymongo.DESCENDING)
	all_data = []
	ct = 0
	for user in full_data:
		ct += 1
		cur_data = {}
		rating = user.get("elo_rating", 1000)
		cgpa_rating = user.get("cgpa_rating", 0)
		name = user.get("Name", "")
		full_name = ""
		if name == "":
			name = False
		else:
			name_prefix = name.get("prefix","")
			name_first = name.get("first_name","")
			name_middle = name.get("middle_name","")
			name_last = name.get("last_name","") 
			if name_prefix == "" and name_last == "" and name_middle == "" and name_first == "":
				name = False
			else:
				full_name = name_prefix + " " + name_first + " " + name_middle + " " + name_last
				full_name = full_name.split()
				full_name = " ".join(full_name)
				name = True
		dob = user.get("DOB",False)
		age = 0
		if dob != False:
			date_of_birth = {}
			date_of_birth["date"] = dob.get("date","")
			date_of_birth["month"] = dob.get("month","")
			date_of_birth["year"] = dob.get("year","")
			if date_of_birth["date"] == "" or date_of_birth["month"] == "" or date_of_birth["year"] == "":
				dob = "Enter your Date of Birth"
			else:
				age = calculate_age(date_of_birth)
		# Update all the data for showing
		cur_data["name"] = full_name
		cur_data["age"] = age
		cur_data["rating"] = rating
		cur_data["cgpa_rating"] = cgpa_rating
		cur_data["rank"] = ct
		all_data.append(cur_data)
	return render_template(
		"ranking.html",
		get_html = Markup(get_html),
		profile_pic = profile_pic, 
		facebook_name = facebook_name, 
		email = Email, 
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
		all_data = all_data,
		logged_in = logged_in
	)