from flask import Blueprint, jsonify, Markup, Flask, render_template, send_from_directory, url_for, session, request, flash, g, redirect
from flask_oauth import OAuth
from flask import session
from decorators import login_required
from werkzeug import secure_filename
from pymongo import MongoClient
from utils import csv_to_json, store_all_predefined_users, read_xlsx, get_size, validate_name, validate_name_prefix, print_html, calculate_age, validate_time
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
from views import facebook
from utils import check_admin
import csv
import shutil

appli = Blueprint("admin", __name__)

def calculate_races():
	races = db.races
	race = races.find({})
	all_races = []
	races_data = []
	ct = 1
	for each_race in race:
		each_race["count"] = ct
		if each_race.get("flag") == "visible":
			all_races.append(each_race)
		races_data.append(each_race)
		ct += 1
	len_all_races = len(races_data)
	return (all_races,races_data,len_all_races)

def calculate_messages():
	# calculate all messages
	messages = db.messages
	message = messages.find({})
	all_messages = []
	ct = 1
	messages_data = []
	for each_message in message:
		each_message["count"] = ct
		if each_message.get("flag") == "visible":
			all_messages.append(each_message)
		messages_data.append(each_message)
		ct += 1
	len_all_messages = len(messages_data)
	return (all_messages,messages_data,len_all_messages)

@facebook.tokengetter
def get_facebook_token():
	return session.get('facebook_token')

# Auth Callback to get the user data after receiving the token
@appli.route("/login_facebook_auth_callback",methods = ["GET","POST"])
@facebook.authorized_handler
def login_facebook_auth_callback(resp):
	next_url = request.args.get("code") or url_for("admin.admin_login")
	if resp is None or "access_token" not in resp:
		return redirect(url_for("admin.admin_login"))
	session["facebook_token"] = (resp["access_token"],"")
	me = facebook.get('/me?fields=id,name,gender,email,picture')
	full_data = me.data
	profile_pic = full_data["picture"]["data"]["url"]
	email = full_data["email"]
	name = full_data["name"]
	session["email"] = email
	session["facebook_name"] = name
	session["profile_pic"] = profile_pic
	# Store User
	
	return redirect(url_for("admin.admin_dashboard"))

@appli.route("/login_with_facebook",methods = ["GET","POST"])
def login_with_facebook():
	return facebook.authorize(callback=url_for('admin.login_facebook_auth_callback',
        next=request.args.get('next'), _external=True))

@appli.route("/admin_logout",methods=["GET","POST"])
def admin_logout():
	session.pop("email",None)
	session.pop("facebook_name",None)
	session.pop("profile_pic",None)
	session.pop("facebook_token",None)
	return redirect(url_for("admin.admin_login"))

@appli.route("/admin_login",methods=["GET","POST"])
def admin_login():
	if "email" not in session:		
		return render_template("admin_login.html")
	else:
		admins = db.admin
		allowed_emails = admins.find({})
		for i in allowed_emails:
			allowed_emails = i["Email"]
		try:
			check_mail = unicode(session["email"], "utf-8")
		except:
			check_mail = session["email"]
		if check_mail in allowed_emails:
			return redirect(url_for("admin.admin_dashboard"))
		else:
			session.pop("email",None)
			session.pop("facebook_name",None)
			session.pop("profile_pic",None)
			session.pop("facebook_token",None)
			return render_template("admin_login.html")
			

@appli.route("/admin_dashboard",methods=["GET","POST"])
def admin_dashboard():
	try:
		check = check_admin(session["email"])
	except:
		return redirect(url_for("admin.admin_login"))
	print 1
	users = db.users
	if check == True:
		try:
			profile_pic = session["profile_pic"]
			facebook_name = session["facebook_name"]
			# Make it true on production
			consider_rider_tag = False
			if consider_rider_tag == False:
				total_registered_users = users.count()
			else:
				pass
			all_users = users.find({})
			total_fully_reg_users = 0
			for cur_rider in all_users:
				flag = 0
				form_personal_profile = cur_rider.get("form_personal_profile",False)
				form_rider_profile = cur_rider.get("form_rider_profile",False)
				form_medical_profile = cur_rider.get("form_medical_profile",False)
				form_bike_profile = cur_rider.get("form_bike_profile",False)
				form_race_profile = cur_rider.get("form_race_profile",False)
				if form_personal_profile == False or form_rider_profile == False or form_bike_profile == False or form_medical_profile == False or form_race_profile == False:
					flag = 1
				if flag == 0:
					total_fully_reg_users += 1
			admins = db.admin
			allowed_emails = admins.find({})
			for i in allowed_emails:
				allowed_emails = i["Email"]
			all_admins = []
			for i in allowed_emails:
				all_admins.append(i.encode('utf-8'))
			return render_template(
				"admin_dashboard.html",
				profile_pic = session["profile_pic"], 
				facebook_name = session["facebook_name"], 
				email = session["email"], 
				total_registered_users = total_registered_users,
				total_fully_reg_users = total_fully_reg_users,
				len_all_races = calculate_races()[2],
				all_admins = all_admins,
			)
		except:
			session.pop("email",None)
			session.pop("facebook_name",None)
			session.pop("profile_pic",None)
			session.pop("facebook_token",None)
			return redirect(url_for("admin.admin_login"))
	else:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))

@appli.route("/admin_upload_csv/<race_name>",methods=["GET","POST"])
def admin_upload_csv(race_name):
	try:
		check = check_admin(session["email"])
	except:
		return redirect(url_for("admin.admin_login"))
	if check == True:
		check_file = os.path.isfile(os.path.join(app.config['UPLOAD_CSV_TEMP'], race_name))
		if check_file == True:
			try:
				profile_pic = session["profile_pic"]
				facebook_name = session["facebook_name"]
				correct_data = False
				wrong_data = True
				error = ""
				notify = ""
				if request.method == "POST":
					db_race_difficulty = int(request.form["db_race_difficulty"].strip())
					db_company_name = str(request.form["db_company_name"]).strip()
					db_company_description = str(request.form["db_company_description"]).strip()
					db_company_number = str(request.form["db_company_number"]).strip()
					db_company_email = str(request.form["db_company_email"]).strip()
					db_company_address_part_one = str(request.form["db_company_address_part_one"]).strip()
					db_company_address_part_two = str(request.form["db_company_address_part_two"]).strip()
					db_company_address_part_three = str(request.form["db_company_address_part_three"]).strip()
					db_company_address_part_four = str(request.form["db_company_address_part_four"]).strip()
					db_company_nation = str(request.form["db_company_nation"]).strip()
					db_race_date = str(request.form["db_race_date"]).strip()
					shutil.copy2(os.path.join(app.config['UPLOAD_CSV_TEMP'], race_name),os.path.join(app.config['UPLOAD_CSV_FINAL'], race_name) )
					os.remove(os.path.join(app.config['UPLOAD_CSV_TEMP'], race_name))
					csv_to_json(
							os.path.join(app.config['UPLOAD_CSV_FINAL'], race_name),
							db_race_difficulty,
							db_company_name,
							db_company_description,
							db_company_number,
							db_company_email,
							db_company_address_part_one,
							db_company_address_part_two,
							db_company_address_part_three,
							db_company_address_part_four,
							db_company_nation,
							db_race_date
					)
					revise_all_ranks()
					notify = "Successfully updated CSV"
					return redirect(url_for("admin.admin_upload_results"))
				return render_template(
					"admin_csv_upload.html",
					profile_pic = session["profile_pic"], 
					facebook_name = session["facebook_name"], 
					email = session["email"], 
					)
			except:
				session.pop("email",None)
				session.pop("facebook_name",None)
				session.pop("profile_pic",None)
				session.pop("facebook_token",None)
				return redirect(url_for("admin.admin_login"))
		else:
			return redirect(url_for("admin.admin_upload_results"))	
	else:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))


@appli.route("/admin_upload_results",methods=["GET","POST"])
def admin_upload_results():
	try:
		check = check_admin(session["email"])
	except:
		return redirect(url_for("admin.admin_login"))
	if check == True:
		try:
			profile_pic = session["profile_pic"]
			facebook_name = session["facebook_name"]
			all_data = []
			fields = []
			admins = db.admin
			correct_data = False
			wrong_data = True
			error = ""
			notify = ""
			if request.method == "POST":
				file = request.files["file"]
				all_data = []
				if file:
					file_name = secure_filename(file.filename)
					filetype = file_name.split(".")[1]
					if filetype == "csv":
						file.save(os.path.join(app.config['UPLOAD_CSV_TEMP'], file_name))
						path_to_csv = os.path.join(app.config['UPLOAD_CSV_TEMP'], file_name)
						open_csv = open(path_to_csv, "rt")
						try:
							reader = csv.reader(open_csv)
							ct = 0
							fields = []
							for row in reader:
								dic = {}
								if ct == 0:
									fields = row[:]
									for i in range(len(fields)):
										fields[i] = fields[i].lower()
								else:
									counter = 0
									for each in row:
										dic[fields[counter]] = each
										counter += 1
									dic["valid"] = True
								ct += 1
								if dic != {}:
									all_data.append(dic)
						except:
							pass
						finally:
							open_csv.close()
						ct = 0
						flag = 0
						for cur_data in all_data:
							for field in cur_data:
								if "name" in field:
									check_name = validate_name(cur_data[field])
									if check_name == False:
										flag = 1
										all_data[ct]["valid"] = False
								if "day" in field:
									if cur_data[field] != "DNF" and cur_data[field] != "dnf" and cur_data[field] != "Dnf":
										check_time = validate_time(cur_data[field])
										if check_time == False:
											flag = 1
											all_data[ct]["valid"] = False
							ct += 1
						if flag == 0:
							correct_data = True
							return redirect(url_for("admin.admin_upload_csv",race_name = file_name))
						else:
							error = "Invalid Data in CSV. Change and upload again."
							wrong_data = False
					else:
						error = "Upload file in CSV format only"
			return render_template(
				"admin_upload_results.html",
				profile_pic = session["profile_pic"], 
				facebook_name = session["facebook_name"], 
				email = session["email"], 
				all_data = all_data,
				fields = fields,
				correct_data = correct_data,
				wrong_data = wrong_data,
				error = error,
				notify = notify
			)
		except:
			session.pop("email",None)
			session.pop("facebook_name",None)
			session.pop("profile_pic",None)
			session.pop("facebook_token",None)
			return redirect(url_for("admin.admin_login"))
	else:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))

@appli.route("/admin_race_notification",methods=["GET","POST"])
def admin_race_notification():
	try:
		check = check_admin(session["email"])
	except:
		return redirect(url_for("admin.admin_login"))
	races = db.races
	if check == True:
		try:
			profile_pic = session["profile_pic"]
			facebook_name = session["facebook_name"]
			if request.method == "POST":
				race_name = str(request.form["race_name"]).strip()
				race_description = str(request.form["race_description"]).strip()
				race_difficulty = str(request.form["race_difficulty"]).strip()
				race = {
						"name" : race_name,
						"difficulty" : int(race_difficulty),
						"description" : race_description,
						"flag" : "not_visible",
						}
				races.insert_one(race)
			compute = calculate_races()
			races_data = compute[1]
			len_all_races = compute[2]
			return render_template(
				"admin_race_notification.html",
				profile_pic = session["profile_pic"], 
				facebook_name = session["facebook_name"], 
				email = session["email"], 
				all_races = races_data,
				len_all_races = len_all_races,
				)
		except:
			session.pop("email",None)
			session.pop("facebook_name",None)
			session.pop("profile_pic",None)
			session.pop("facebook_token",None)
			return redirect(url_for("admin.admin_login"))
	else:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))

@appli.route("/admin_race_delete_row",methods=["POST"])
def admin_race_delete_row():
	try:
		races = db.races
		races.delete_one(
				{
					"_id" : ObjectId(request.json["id"])
				}
			)
		return "SUCCESS"
	except:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))

@appli.route("/admin_race_edit_row",methods=["POST"])
def admin_race_edit_row():
	try:
		races = db.races
		races.update_one(
				{
					"_id" : ObjectId(request.json["id"])
				},
				{
				"$set" : 
					{
					"flag" : request.json["visibility"]
					}
				}
			)
		return "SUCCESS"
	except:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))

@appli.route("/admin_message_notification",methods=["GET","POST"])
def admin_message_notification():
	try:
		check = check_admin(session["email"])
	except:
		return redirect(url_for("admin.admin_login"))
	messages = db.messages
	if check == True:
		try:
			profile_pic = session["profile_pic"]
			facebook_name = session["facebook_name"]
			if request.method == "POST":
				msg_body = str(request.form["msg_body"]).strip()
				msg_topic = str(request.form["msg_topic"]).strip()
				message = {
						"body" : msg_body,
						"topic" : msg_topic,
						"flag" : "not_visible",
						}
				messages.insert_one(message)
			compute = calculate_messages()
			messages_data = compute[1]
			len_all_messages = compute[2]
			return render_template(
				"admin_message_notification.html",
				profile_pic = session["profile_pic"], 
				facebook_name = session["facebook_name"], 
				email = session["email"], 
				messages_data = messages_data,
				len_all_messages = len_all_messages,
				)
		except:
			session.pop("email",None)
			session.pop("facebook_name",None)
			session.pop("profile_pic",None)
			session.pop("facebook_token",None)
			return redirect(url_for("admin.admin_login"))
	else:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))

@appli.route("/admin_message_delete_row",methods=["POST"])
def admin_message_delete_row():
	try:
		messages = db.messages
		messages.delete_one(
				{
					"_id" : ObjectId(request.json["id"])
				}
			)
		return "SUCCESS"
	except:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))

@appli.route("/admin_message_edit_row",methods=["POST"])
def admin_message_edit_row():
	try:
		messages = db.messages
		messages.update_one(
				{
					"_id" : ObjectId(request.json["id"])
				},
				{
				"$set" : 
					{
					"flag" : request.json["visibility"]
					}
				}
			)
		return "SUCCESS"
	except:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))


@appli.route("/admin_tag_riders",methods=["GET","POST"])
def admin_tag_riders():
	try:
		check = check_admin(session["email"])
	except:
		return redirect(url_for("admin.admin_login"))
	users = db.users
	results = db.results
	race_name = "Hero_MTB_Himalaya_2016"
	if check == True:
		try:
			profile_pic = session["profile_pic"]
			facebook_name = session["facebook_name"]
			
			race_details = results.find_one(
					{
						"race_name" : str(race_name)
					}
				)
			straight_match = {}
			multiple_matches = {}
			for cur_ser_num in race_details["race_result"]:
				if race_details["race_result"][cur_ser_num]["rider_tag"] != "":
					straight_match[cur_ser_num] = {
						"rider_tag" : race_details["race_result"][cur_ser_num]["rider_tag"],
						"name" : race_details["race_result"][cur_ser_num]["name"]
						}
				else:
					name = race_details["race_result"][cur_ser_num]["name"]
					calculate_name = name.split()
					if len(calculate_name) > 1:
						if "." in calculate_name[0]:
							calculate_name = calculate_name[1]
						else:
							calculate_name = calculate_name[0]
					else:
						try:
							calculate_name = calculate_name[0]
						except:
							calculate_name = ""
					all_riders = users.find({})
					cur_match = []
					for cur_rider in all_riders:
						cur_rider_name = ""
						prefix = cur_rider["Name"]["prefix"]
						first_name = cur_rider["Name"]["first_name"]
						middle_name = cur_rider["Name"]["middle_name"]
						last_name = cur_rider["Name"]["last_name"]
						if prefix != "":
							cur_rider_name += prefix + " "
						if first_name != "":
							cur_rider_name += first_name + " "
						if middle_name != "":
							cur_rider_name += middle_name + " "
						if last_name != "":
							cur_rider_name += last_name + " "
						tag = str(cur_rider["_id"])
						if calculate_name.lower() == first_name.lower():
							cur_match.append({
								"name" : cur_rider_name,
								"rider_tag" : tag
								})
					multiple_matches[cur_ser_num] = {
						"name" : name,
						"possible_matches" : cur_match
					}
		
			return "a"
		except:
			#session.pop("email",None)
			#session.pop("facebook_name",None)
			#session.pop("profile_pic",None)
			#session.pop("facebook_token",None)
			return redirect(url_for("admin.admin_login"))
	else:
		session.pop("email",None)
		session.pop("facebook_name",None)
		session.pop("profile_pic",None)
		session.pop("facebook_token",None)
		return redirect(url_for("admin.admin_login"))
