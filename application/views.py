from flask import Blueprint, jsonify, Markup, Flask, render_template, send_from_directory, url_for, session, request, flash, g, redirect
from flask_oauth import OAuth
from flask import session
from decorators import login_required
from werkzeug import secure_filename
from pymongo import MongoClient
from utils import csv_to_json, store_all_predefined_users, read_xlsx, get_size, validate_name, validate_name_prefix, print_html, calculate_age
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

appli = Blueprint('views', __name__)
number_list = ["0","1","2","3","4","5","6","7","8","9"]

# calculate all races
races = db.races
messages = db.messages

def calculate_races_messages():
	race = races.find({})
	all_races = []
	for each_race in race:
		if each_race.get("flag") == "visible":
			all_races.append(each_race)

	# calculate all messages
	message = messages.find({})
	all_messages = []
	for each_message in message:
		if each_message.get("flag") == "visible":
			all_messages.append(each_message)
	len_all_races = len(all_races)
	len_all_messages = len(all_messages)
	return (all_races,all_messages,len_all_races,len_all_messages)

FACEBOOK_APP_ID = "1187825241331167"
FACEBOOK_APP_SECRET = "cb11302898c0cc747f0f24cc28c0b55c"

facebook = oauth.remote_app('facebook',
    base_url='https://graph.facebook.com/',
    request_token_url=None,
    access_token_url='/oauth/access_token',
    authorize_url='https://www.facebook.com/dialog/oauth',
    consumer_key=FACEBOOK_APP_ID,
    consumer_secret=FACEBOOK_APP_SECRET,
    request_token_params={'scope': ('email, ')}
)

@facebook.tokengetter
def get_facebook_token():
	return session.get('facebook_token')

# Auth Callback to get the user data after receiving the token
@appli.route("/facebook_auth_callback",methods = ["GET","POST"])
@facebook.authorized_handler
def facebook_auth_callback(resp):
	next_url = request.args.get("code") or url_for("views.homepage")
	if resp is None or "access_token" not in resp:
		return redirect(url_for("views.homepage"))
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
	users = db.users
	check_email = users.find_one({"Email" : email})
	# store the user if not already there
	if check_email is None:
		user = {
		"Email" : email,
		"facebook_name" : name,
		"profile_pic" : profile_pic ,
		"elo_rating" : 1000
		}
		users.insert_one(user)
	return redirect(url_for("views.userhome"))

@appli.route("/signup_with_facebook",methods = ["GET","POST"])
def signup_with_facebook():
	return facebook.authorize(callback=url_for('views.facebook_auth_callback',
        next=request.args.get('next'), _external=True))

# User Dashboard (profiling)
@appli.route("/userhome",methods=["GET","POST"])
@login_required
def userhome():
	users = db.users
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	user = users.find_one({"Email":session["email"]})
	check_registered = "Unregistered"
	if "DOB" in user:
		check_registered = "Registered"
	profile_pic = user.get("profile_pic",None)
	facebook_name = user.get("facebook_name",None)
	image = user.get("image","")
	if image == "":
		session["profile_pic"] = profile_pic
		(width, height) = (0,100)
	else:
		session["profile_pic"] = "static/img/profile_images/" + image + "?r=" + str(randint(1,10000000))
		var = session["profile_pic"]
		if "?" in var : 
			var = var.split("?")[0]
		var = ROOT_DIR + "/" + var
		(width, height) = get_size(var)
	session["facebook_name"] = facebook_name
	get_html = print_html(session["profile_pic"],session["facebook_name"],height,session["email"])
	participation = user.get("participation",False)
	if participation != False:
		participation = participation.split(",")
	podiums = user.get("podiums",False)
	if podiums != False:
		podiums = podiums.split(",")
	name = user.get("Name","")
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
	name_alias = user.get("name_alias","Enter your Alias")
	Mobile = user.get("Mobile","Enter your Mobile Number")
	address = user.get("address","Enter your Address")
	full_address = ""
	map_address = ""
	if address != "Enter your Address":
		address_part_one = address.get("address1","")
		address_part_two = address.get("address2","")
		address_part_three = address.get("state","")
		address_part_four = address.get("country","")
		full_address = address_part_one + ", " + address_part_two + ", " + address_part_three + ", " + address_part_four
		map_address = address_part_two + ", " + address_part_three + ", " + address_part_four
	emergency_contact = user.get("emergency_contact","Enter your Emergency Contact")
	relation = ""
	relation_name = ""
	relation_contact = ""
	if emergency_contact != "Enter your Emergency Contact":
		relation = emergency_contact.get("relation","")
		relation_name = emergency_contact.get("relation_name","")
		relation_contact = emergency_contact.get("relation_contact_number","")
		emergency_contact = True
	else:
		emergency_contact = False
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
	blood_group = user.get("Blood Group",False)
	nationality = user.get("Nationality",False)
	reg_id = str(user.get("_id",""))
	path_id_proof = user.get("id_proof","")
	download_id_proof = ""
	download_rider_insurance = ""
	download_rider_id_proof = ""
	if path_id_proof != "":
		download_id_proof = "id_proof." + path_id_proof.split(".")[1]
		path_id_proof = "/static/id_proof/" + path_id_proof
	path_rider_insurance = user.get("rider_insurance_certificate","")
	if path_rider_insurance != "":
		download_rider_insurance = "medical_insurance_certificate." + path_rider_insurance.split(".")[1]
		path_rider_insurance = "/static/rider_insurance_certificate/" + path_rider_insurance
 	path_rider_id_proof = user.get("rider_id_proof","")
 	if path_rider_id_proof != "":
 		download_rider_id_proof = "rider_id_proof." + path_rider_id_proof.split(".")[1]
 		path_rider_id_proof = "/static/rider_id_proof/" + path_rider_id_proof
 	allergy = user.get("Allergy",False)
 	if allergy != False:
 		allergy = allergy.split(",")
 	bike_details = user.get("bike_details",False)
 	bike_brand = ""
 	bike_size = ""
 	bike_style = []
 	bike_brand_other_input = ""
 	if bike_details != False:
 		bike_brand = bike_details.get("bike_brand","")
 		bike_size = bike_details.get("bike_size","")
 		bike_style = bike_details.get("bike_style",[])
 		if bike_style != []:
 			bike_style = ",".join(bike_style)
 		bike_brand_other_input = bike_details.get("bike_brand_other_input","")
 	riding_style = user.get("riding_style",[])
 	if riding_style == []:
 		check_riding_style = False
 	else:
 		check_riding_style = True
 	sponsors = user.get("sponsors",False)
 	if sponsors != False:
	 	sponsors = sponsors.split(",")
	team_name = user.get("team_name",False)
	rider_type = user.get("rider_type",False)
	uci_status = user.get("uci_status",False)
	uci_id = ""
	if uci_status != False:
		if uci_status == "yes":
			uci_id = user.get("uci_id","")
	jersey_size = user.get("Jerseey size",False)
	# check for fully registered or not
	form_personal_profile = user.get("form_personal_profile",False)
	form_rider_profile = user.get("form_rider_profile",False)
	form_medical_profile = user.get("form_medical_profile",False)
	form_bike_profile = user.get("form_bike_profile",False)
	form_race_profile = user.get("form_race_profile",False)
	forms_not_completed = []
	if form_personal_profile == False:
		form_not_completed = {}
		form_not_completed["name"] = "Form Personal Profile"
		form_not_completed["url"] = "/form_personal_profile"
		forms_not_completed.append(form_not_completed)
	if form_race_profile == False:
		form_not_completed = {}
		form_not_completed["name"] = "Form Race Profile"
		form_not_completed["url"] = "/form_race_profile"
		forms_not_completed.append(form_not_completed)
	if form_bike_profile == False:
		form_not_completed = {}
		form_not_completed["name"] = "Form Bike Profile"
		form_not_completed["url"] = "/form_bike_profile"
		forms_not_completed.append(form_not_completed)
	if form_rider_profile == False:
		form_not_completed = {}
		form_not_completed["name"] = "Form Rider Profile"
		form_not_completed["url"] = "/form_rider_profile"
		forms_not_completed.append(form_not_completed)
	if form_medical_profile == False:
		form_not_completed = {}
		form_not_completed["name"] = "Form Medical Profile"
		form_not_completed["url"] = "/form_medical_profile"
		forms_not_completed.append(form_not_completed)
	dream_bike = user.get("dream_bike","Complete the form")
	dream_bike_brand = user.get("dream_bike_brand","Complete the form")
	first_bike = user.get("first_bike","Complete the form")
	often_rides = user.get("often_rides","Complete the form")
	fav_trail = user.get("fav_trail","Complete the form")
	dream_trail = user.get("dream_trail","Complete the form")
	best_exp = user.get("best_exp","Complete the form")
	return render_template(
		"dashboard.html", 
		profile_pic = session["profile_pic"], 
		facebook_name = facebook_name, 
		email = session["email"], 
		check_registered = check_registered,
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
		width = width,
		height = height,
		get_html = Markup(get_html),
		participation = participation,
		podiums = podiums,
		full_name = full_name,
		name_alias = name_alias,
		Mobile = Mobile,
		full_address = full_address,
		relation = relation,
		relation_name = relation_name,
		relation_contact = relation_contact,
		name = name,
		emergency_contact = emergency_contact,
		age = age,
		reg_id = reg_id,
		nationality = nationality,
		blood_group = blood_group,
		path_id_proof = path_id_proof,
		path_rider_insurance = path_rider_insurance,
		download_rider_insurance = download_rider_insurance,
		download_id_proof = download_id_proof,
		allergy = allergy,
		bike_brand = bike_brand,
		bike_style = bike_style,
		bike_size = bike_size,
		map_address = map_address,
		bike_brand_other_input = bike_brand_other_input,
		bike_details = bike_details,
		riding_style = riding_style,
		check_riding_style = check_riding_style,
		sponsors = sponsors,
		team_name = team_name,
		rider_type = rider_type,
		jersey_size = jersey_size,
		uci_status = uci_status,
		uci_id = uci_id,
		path_rider_id_proof = path_rider_id_proof,
		download_rider_id_proof = download_rider_id_proof,
		forms_not_completed = forms_not_completed,
		total_forms_completed = 5 - len(forms_not_completed),
		percentage_completion = (5 - len(forms_not_completed))*20,
		dream_bike = dream_bike,
		dream_bike_brand = dream_bike_brand,
		first_bike = first_bike,
		often_rides = often_rides,
		fav_trail = fav_trail,
		dream_trail = dream_trail,
		best_exp = best_exp
		)

@appli.route("/form_personal_profile",methods=["GET","POST"])
@login_required
def form_personal_profile():
	users = db.users
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	error = ""
	if request.method == "POST":
		name_prefix = str(request.form["name_prefix"]).strip()
		name_first = str(request.form["name_first"]).strip()
		name_middle = str(request.form["name_middle"]).strip()
		mobile_number = str(request.form["mobile"]).strip()
		name_last = str(request.form["name_last"]).strip()
		gender = str(request.form["gender"]).strip()
		name_father = str(request.form["name_father"]).strip()
		address_part_one = str(request.form["address_part_one"]).strip()
		address_part_two = str(request.form["address_part_two"]).strip()
		address_part_three = str(request.form["address_part_three"]).strip()
		address_part_four = str(request.form["address_part_four"]).strip()
		nationality = str(request.form["nation"]).strip()
		dob = str(request.form["dob"]).strip()
		dob = dob.split("-")[::-1]
		flag = 0
		for i in dob:
			try:
				check_int = int(i)
			except:
				flag = 1
				error = "Correct the date"
		if flag == 0 and datetime.datetime(year=int(dob[2]),month=int(dob[1]),day=int(dob[0])) > datetime.datetime.now():
			error = "Date exceeds today"
		try:
			file = request.files["file"]
		except RequestEntityTooLarge:
			flash('File size too large.  Limit is 1 MB.')
			error = "File size too large.  Limit is 1 MB."
		try:
			id_file = request.files["filename"]
		except RequestEntityTooLarge:
			flash('File size too large.  Limit is 1 MB.')
			error = "File size too large.  Limit is 1 MB."
		user = users.find_one({"Email":session["email"]})
		check_for_image = user.get("image", None)
		new_mobile_number = "+"
		for i in mobile_number:
			if i in number_list:
				new_mobile_number += i
		mobile_number = new_mobile_number 
		error = ""
		# Backend Validation 

		if validate_name_prefix(name_prefix) == False:
			error = "Enter Correct name prefix (only characters accepted)"
		if validate_name(name_first) == False:
			error = "Enter Correct first name (only characters accepted)"
		if validate_name(name_middle) == False:
			error = "Enter Correct middle name (only characters accepted)"
		if validate_name(name_last) == False:
			error = "Enter Correct last name (only characters accepted)"
		if validate_name(name_father) == False:
			error = "Enter Correct father name (only characters accepted)"
		if name_middle != "":
			if name_last == "":
				error = "Enter Last Name Also"
		if name_first == "" or name_last == "" or name_father == "" or address_part_four == "" or address_part_three == "" or address_part_two == "" or address_part_one == "" or mobile_number == "" or nationality == "" or dob == "":
			error = "Please enter all the details"
		if error == "":
			# Saving and uploading the file 
			if file:
				file_name = secure_filename(file.filename)
				filetype = file_name.split(".")[1]
				if filetype == "jpg" or filetype == "png" or filetype == "bmp":
					actual_filename = str(user.get("_id")) + "." + filetype
					file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_name))
					os.rename(os.path.join(app.config['UPLOAD_FOLDER'], file_name),os.path.join(app.config['UPLOAD_FOLDER'], actual_filename))
					users.update_one(
						{"Email":session["email"]},
							{ "$set" : {
							"image": actual_filename
					}})
			check_for_file = user.get("id_proof", None)
			if id_file:
				if check_for_file is not None:
					os.remove(app.config['UPLOAD_FOLDER_ID'] + check_for_file)
				file_name = secure_filename(id_file.filename)
				filetype = file_name.split(".")[1]
				if filetype == "jpg" or filetype == "png" or filetype == "bmp" or filetype == "doc" or filetype == "docx" or filetype == "pdf":
					actual_filename = str(user.get("_id")) + "." + filetype			
					id_file.save(os.path.join(app.config['UPLOAD_FOLDER_ID'], file_name))
					os.rename(os.path.join(app.config['UPLOAD_FOLDER_ID'], file_name),os.path.join(app.config['UPLOAD_FOLDER_ID'], actual_filename))
					users.update_one(
						{"Email":session["email"]},
							{ "$set" : {
							"id_proof": actual_filename
					}})
			# update the details
			users.update_one(
				{"Email":session["email"]},
				{ "$set" : {
						"Name" : {
									"prefix" : name_prefix,
									"first_name" : name_first,
									"middle_name" : name_middle,
									"last_name" : name_last
								},	
						"address" : {
									"address1" : address_part_one,
									"address2" : address_part_two,
									"state" : address_part_three,
									"country" : address_part_four
								},
						"Nationality" : nationality,
						"Gender" : gender,
						"father_name" : name_father,
						"DOB" : {
									"date" : int(dob[0]),
									"month" : int(dob[1]),
									"year" : int(dob[2])
								},
						"Mobile" : mobile_number,
						"form_personal_profile" : True
						}
					}
				)
	# get the details
	user = users.find_one({"Email":session["email"]})
	mobile_number = user.get("Mobile","")
	name = user.get("Name",None)
	if name is None:
		name_prefix = ""
		name_first = ""
		name_last = ""
		name_middle = ""
	else:
		name_prefix = name.get("prefix","")
		name_middle = name.get("middle_name","")
		name_last = name.get("last_name","")
		name_first = name.get("first_name","")
	address = user.get("address",None)
	if address is None:
		address_part_one = ""
		address_part_four = ""
		address_part_three = ""
		address_part_two = ""
	else:
		address_part_one = address.get("address1","")
		address_part_four = address.get("country","")
		address_part_three = address.get("state","")
		address_part_two = address.get("address2","")
	get_id_proof = user.get("id_proof",None)
	get_image = user.get("image",None)
	if get_image != None and get_image != "":
		session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
		var = session["profile_pic"]
		if "?" in var : 
			var = var.split("?")[0]
		var = ROOT_DIR + "/" + var
		(width, height) = get_size(var)
	else:
		(width, height) = (0,100)
	get_html = print_html(session["profile_pic"],session["facebook_name"],height,session["email"])
	gender = user.get("Gender","")
	nationality = user.get("Nationality","")
	name_father = user.get("father_name","")
	dob = user.get("DOB",None)
	if dob is None:
		date = 03
		month = 06
		year = 1995
	else:
		date = dob.get("date",03)
		month = dob.get("month",06)
		year = dob.get("year",1995)
	date_of_birth = str(year) + "-" + str(month) + "-" + str(date)
	image_uploaded = user.get("image","")
	if image_uploaded != "":
		image_uploaded = "Already Uploaded"
	else:
		image_uploaded = "Upload file"
	id_proof_uploaded = user.get("id_proof","")
	if id_proof_uploaded != "":
		id_proof_uploaded = "Already Uploaded"
	else:
		id_proof_uploaded = "Upload file"
	return render_template(
		"form_personal_profile.html",
		profile_pic = session["profile_pic"], 
		facebook_name = session["facebook_name"], 
		email = session["email"], 
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
		name_prefix = name_prefix,
		name_first = name_first,
		name_middle = name_middle,
		get_id_proof = get_id_proof,
		name_last = name_last,
		address_part_one = address_part_one,
		address_part_four = address_part_four,
		address_part_three = address_part_three,
		address_part_two = address_part_two,
		gender = gender,
		nationality = nationality,
		name_father = name_father,
		date_of_birth = date_of_birth,
		width = width,
		height = height,
		mobile_number = mobile_number,
		error = error,
		image_uploaded = image_uploaded,
		id_proof_uploaded = id_proof_uploaded,
		get_html = Markup(get_html)
		)

@appli.route("/form_rider_profile",methods=["GET","POST"])
@login_required
def form_rider_profile():
	error = ""
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	users = db.users
	if request.method == "POST":
		name_alias = str(request.form["name_alias"]).strip()
		rider_type = str(request.form["rider_type"]).strip()
		rider_type_other_input = ""
		if rider_type == "other":
			rider_type_other_input = str(request.form["rider_type_other_input"]).strip()
			rider_type = rider_type_other_input
		
		riding_style = request.form.getlist("riding_style")
		rider_id_file = request.files["rider_id"]
		uci_status = str(request.form["uci_status"]).strip()
		uci_id = ""
		if uci_status == "yes":
			uci_id = str(request.form["uci_id"]).strip()
		team_name = str(request.form["team_name"]).strip()
		sponsors = str(request.form["sponsors"]).strip()
		jersey_size = str(request.form["jersey_size"]).strip()
		first_bike = str(request.form["first_bike"]).strip()
		often_rides = int(request.form["often_rides"])
		fav_trail = str(request.form["fav_trail"]).strip()
		dream_trail = str(request.form["dream_trail"]).strip()
		best_exp = str(request.form["best_exp"]).strip()
		
		user = users.find_one({"Email":session["email"]})
		check_for_file = user.get("rider_id_proof", None)
		error = ""
		if team_name == "" or rider_type == "" or name_alias == "" or first_bike == "" or often_rides == "" or fav_trail == "" or dream_trail == "" or best_exp == "":
			error = "Fill all the details"
		if uci_status == "yes":
			if uci_id == "":
				error = "Fill uci id"
		if rider_type == "other":
			if rider_type_other_input == "":
				error = "Enter other rider type"
		if error == "":
			if rider_id_file:
				if check_for_file is not None:
					os.remove(app.config['UPLOAD_FOLDER_ID_RIDER'] + check_for_file)
				file_name = secure_filename(rider_id_file.filename)
				filetype = file_name.split(".")[1]
				if filetype == "jpg" or filetype == "png" or filetype == "bmp" or filetype == "doc" or filetype == "docx" or filetype == "pdf":
					actual_filename = str(user.get("_id")) + "." + filetype
					rider_id_file.save(os.path.join(app.config['UPLOAD_FOLDER_ID_RIDER'], file_name))
					os.rename(os.path.join(app.config['UPLOAD_FOLDER_ID_RIDER'], file_name),os.path.join(app.config['UPLOAD_FOLDER_ID_RIDER'], actual_filename))
					users.update_one(
						{"Email":session["email"]},
							{ "$set" : {
							"rider_id_proof": actual_filename
					}})
			users.update_one(
				{"Email":session["email"]},
				{ "$set" : {
						"name_alias" : name_alias,	
						"rider_type" : rider_type,
						"riding_style" : riding_style,
						"sponsors" : sponsors,
						"uci_status" : uci_status,
						"uci_id" : uci_id,
						"team_name" : team_name,
						"Jerseey size" : jersey_size,
						"form_rider_profile" : True,
						"first_bike" : first_bike,
						"often_rides" : often_rides,
						"fav_trail" : fav_trail,
						"dream_trail" : dream_trail,
						"best_exp" : best_exp
						}
					}
				)
	user = users.find_one({"Email":session["email"]})
	name_alias = user.get("name_alias","")
	rider_type = user.get("rider_type","")
	riding_style = user.get("riding_style",[])
	get_rider_id_proof = user.get("rider_id_proof",None)
	sponsors = user.get("sponsors","")
	uci_status = user.get("uci_status","")
	uci_id = user.get("uci_id","")
	team_name = user.get("team_name","")
	jersey_size = user.get("Jerseey size","")
	first_bike = user.get("first_bike","")
	often_rides = user.get("often_rides","")
	fav_trail = user.get("fav_trail","")
	dream_trail = user.get("dream_trail","")
	best_exp = user.get("best_exp","")
	get_image = user.get("image",None)
	if get_image != None:
		session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
		var = session["profile_pic"]
		if "?" in var : 
			var = var.split("?")[0]
		var = ROOT_DIR + "/" + var
		(width, height) = get_size(var)
	else:
		(width, height) = (0,100)
	rider_id_proof_uploaded = user.get("rider_id_proof","")
	if rider_id_proof_uploaded != "":
		rider_id_proof_uploaded = "Already Uploaded"
	else:
		rider_id_proof_uploaded = "Upload file"
	get_html = print_html(session["profile_pic"],session["facebook_name"],height,session["email"])
	return render_template(
		"form_rider_profile.html",
		profile_pic = session["profile_pic"], 
		facebook_name = session["facebook_name"], 
		email = session["email"], 
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
		name_alias = name_alias,
		rider_type = rider_type,
		riding_style = riding_style,
		get_rider_id_proof = get_rider_id_proof,
		sponsors = sponsors,
		uci_status = uci_status,
		uci_id = uci_id,
		team_name = team_name,
		jersey_size = jersey_size,
		width = width,
		height = height,
		error = error,
		rider_id_proof_uploaded = rider_id_proof_uploaded,
		get_html = Markup(get_html),
		first_bike = first_bike,
		often_rides = often_rides,
		fav_trail = fav_trail,
		dream_trail = dream_trail,
		best_exp = best_exp,
		)

@appli.route("/form_medical_profile",methods=["GET","POST"])
@login_required
def form_medical_profile():
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	users = db.users
	error = ""
	if request.method == "POST":
		blood_group = str(request.form["blood_group"]).strip()
		allergies = str(request.form["allergies"]).strip()
		rider_insurance_certificate = request.files["rider_insurance_certificate"]
		emg_name = str(request.form["emg_name"]).strip()
		emg_number = str(request.form["emg_number"]).strip()
		emg_relation = str(request.form["emg_relation"]).strip()
		error = ""
		if validate_name_prefix(emg_name) == False:
			error = "Correct the emergency person's name"
		if blood_group == "" or emg_name == "" or emg_relation == "" or emg_number == "": 
			error = "Fill all the required details"
		user = users.find_one({"Email":session["email"]})
		check_for_file = user.get("rider_insurance_certificate", None)
		if error == "":
			if rider_insurance_certificate:
				if check_for_file is not None:
					os.remove(app.config['UPLOAD_FOLDER_ID_RIDER_INSURANCE'] + check_for_file)
				file_name = secure_filename(rider_insurance_certificate.filename)
				filetype = file_name.split(".")[1]
				if filetype == "jpg" or filetype == "png" or filetype == "bmp" or filetype == "doc" or filetype == "docx" or filetype == "pdf":
					actual_filename = str(user.get("_id")) + "." + filetype
					rider_insurance_certificate.save(os.path.join(app.config['UPLOAD_FOLDER_ID_RIDER_INSURANCE'], file_name))
					os.rename(os.path.join(app.config['UPLOAD_FOLDER_ID_RIDER_INSURANCE'], file_name),os.path.join(app.config['UPLOAD_FOLDER_ID_RIDER_INSURANCE'], actual_filename))
					users.update_one(
						{"Email":session["email"]},
							{ "$set" : {
							"rider_insurance_certificate": actual_filename
					}})
			users.update_one(
				{"Email":session["email"]},
				{ "$set" : {
						"emergency_contact" : {
							"relation_contact_number" : emg_number,
							"relation_name" : emg_name,
							"relation" : emg_relation
							},	
						"Blood Group" : blood_group,
						"Allergy" : allergies,
						"form_medical_profile" : True
						}
					}
				)
	user = users.find_one({"Email":session["email"]})
	emergency_contact = user.get("emergency_contact",None)
	if emergency_contact is None:
		emg_name = ""
		emg_relation = ""
		emg_number = ""
	else:
		emg_name = emergency_contact.get("relation_name","")
		emg_number = emergency_contact.get("relation_contact_number","")
		emg_relation = emergency_contact.get("relation","")
	blood_group = user.get("Blood Group","")
	allergies = user.get("Allergy","")
	get_image = user.get("image",None)
	get_rider_insurance_certificate = user.get("rider_insurance_certificate",None)
	# check for uploaded image 
	if get_image != None:
		session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
		var = session["profile_pic"]
		if "?" in var : 
			var = var.split("?")[0]
		var = ROOT_DIR + "/" + var
		(width, height) = get_size(var)
	else:
		(width, height) = (0,100)
	rider_insurance_uploaded = user.get("rider_insurance_certificate","")
	if rider_insurance_uploaded != "":
		rider_insurance_uploaded = "Already Uploaded"
	else:
		rider_insurance_uploaded = "Upload file"
	get_html = print_html(session["profile_pic"],session["facebook_name"],height,session["email"])
	return render_template(
		"form_medical_profile.html",
		profile_pic = session["profile_pic"], 
		facebook_name = session["facebook_name"], 
		email = session["email"], 
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
		allergies = allergies,
		blood_group = blood_group,
		get_rider_insurance_certificate = get_rider_insurance_certificate,
		emg_name = emg_name,
		emg_number = emg_number,
		emg_relation = emg_relation,
		width = width,
		height = height,
		error = error,
		rider_insurance_uploaded = rider_insurance_uploaded,
		get_html = Markup(get_html)
		)

@appli.route("/form_bike_profile",methods=["GET","POST"])
@login_required
def form_bike_profile():
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	error = ""
	users = db.users
	if request.method == "POST":
		bike_brand = str(request.form["bike_brand"]).strip()
		bike_brand_other_input = ""
		if bike_brand == "other":
			bike_brand_other_input = request.form["bike_brand_other_input"]
		bike_style = request.form.getlist("bike_style")
		bike_size = str(request.form["bike_size"]).strip()	
		dream_bike = str(request.form["dream_bike"]).strip()
		dream_bike_brand = str(request.form["dream_bike_brand"]).strip()
		error = ""
		if bike_brand == "other":
			if bike_brand_other_input == "":
				error = "Enter bike brand"
		if bike_brand == "" or bike_style == "" or bike_size == "" or dream_bike == "" or dream_bike_brand == "": 
			error = "Enter required details"
		if error == "":
			users.update_one(
				{"Email":session["email"]},
				{ "$set" : {
						"bike_details" : {
							"bike_brand" : bike_brand,
							"bike_style" : bike_style,
							"bike_size" : bike_size,
							"bike_brand_other_input" : bike_brand_other_input
							},
						"form_bike_profile" : True,
						"dream_bike" : dream_bike,
						"dream_bike_brand" : dream_bike_brand
						}
					}
				)
	user = users.find_one({"Email":session["email"]})
	dream_bike = user.get("dream_bike","")
	dream_bike_brand = user.get("dream_bike_brand","")
	bike_details = user.get("bike_details",None)
	if bike_details is None:
		bike_brand = ""
		bike_size = ""
		bike_style = []
		bike_brand_other_input = ""
	else:
		bike_size = bike_details.get("bike_size","")
		bike_brand = bike_details.get("bike_brand","")
		bike_style = bike_details.get("bike_style","")
		bike_brand_other_input = bike_details.get("bike_brand_other_input",[])
	get_image = user.get("image",None)
	if get_image != None:
		session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
		var = session["profile_pic"]
		if "?" in var : 
			var = var.split("?")[0]
		var = ROOT_DIR + "/" + var
		(width, height) = get_size(var)
	else:
		(width, height) = (0,100)
	get_html = print_html(session["profile_pic"],session["facebook_name"],height,session["email"])
	return render_template(
		"form_bike_profile.html",
		profile_pic = session["profile_pic"], 
		facebook_name = session["facebook_name"], 
		email = session["email"], 
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
		bike_brand = bike_brand,
		bike_brand_other_input = bike_brand_other_input,
		bike_size = bike_size,
		bike_style = bike_style,
		width = width,
		height = height,
		error = error,
		get_html = Markup(get_html),
		dream_bike_brand = dream_bike_brand,
		dream_bike = dream_bike,
		)

@appli.route("/form_race_profile",methods = ["GET","POST"])
@login_required
def form_race_profile():
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	users = db.users
	if request.method == "POST":
		podiums = str(request.form["podiums"]).strip()
		participation = str(request.form["participation"]).strip()
		users.update_one(
			{"Email":session["email"]},
			{ "$set" : {
					"podiums" : podiums,
					"participation" : participation,
					"form_race_profile" : True
					}
				}
			)
	user = users.find_one({"Email":session["email"]})
	session["facebook_name"] = user.get("facebook_name","")
	podiums = user.get("podiums","")
	participation = user.get("participation","")
	get_image = user.get("image",None)
	if get_image != None:
		session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
		var = session["profile_pic"]
		if "?" in var : 
			var = var.split("?")[0]
		var = ROOT_DIR + "/" + var
		(width, height) = get_size(var)
	else:
		(width, height) = (0,100)
	get_html = print_html(session["profile_pic"],session["facebook_name"],height,session["email"])
	return render_template(
		"form_race_profile.html",
		profile_pic = session["profile_pic"], 
		facebook_name = session["facebook_name"], 
		email = session["email"], 
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
		width = width,
		height = height,
		podiums = podiums,
		participation = participation,
		get_html = Markup(get_html)
		)

# 413 when request entity or file is too large
@appli.errorhandler(413)
def error413(e):
	users = db.users
	all_races_messages = calculate_races_messages()
	all_races = all_races_messages[0]
	all_messages = all_races_messages[1]
	len_all_races = all_races_messages[2]
	len_all_messages = all_races_messages[3]
	user = users.find_one({"Email":session["email"]})
	session["facebook_name"] = user.get("facebook_name","")
	get_image = user.get("image",None)
	if get_image != None:
		session["profile_pic"] = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
		var = session["profile_pic"]
		if "?" in var : 
			var = var.split("?")[0]
		var = ROOT_DIR + "/" + var
		(width, height) = get_size(var)
	else:
		(width, height) = (0,100)
	get_html = print_html(session["profile_pic"],session["facebook_name"],height,session["email"])
	return render_template(
    	'413.html',
    	get_html = Markup(get_html),
    	profile_pic = session["profile_pic"], 
		facebook_name = session["facebook_name"], 
		email = session["email"], 
		all_races = all_races,
		len_all_races = len_all_races,
		all_messages = all_messages,
		len_all_messages = len_all_messages,
    	), 413

# login via facebook
@appli.route("/login",methods = ["GET","POST"])
def login():
	if "email" not in session:		
		return render_template("login.html")
	else:
		return redirect(url_for("views.userhome"))

@appli.route("/logout",methods=["GET","POST"])
def logout():
	session.pop("email",None)
	session.pop("facebook_name",None)
	session.pop("profile_pic",None)
	session.pop("facebook_token",None)
	return redirect(url_for("views.homepage"))

# Rider Search acc to name,number,alias,email
@appli.route("/rider_search",methods=["GET","POST"])
def rider_search():
	users = db.users
	logged_in = False
	(width, height) = (0,100)
	if "email" in session:
		logged_in = True
	# argument passing
	search_rider = str(request.args.get("search_rider",None)).strip()
	output = []
	if search_rider == "None" or search_rider == "":
		output = "No Rider Found"
	else:
		search_rider = search_rider.split(" ")
		final_matches = []
		flag = 0
		rider = search_rider[0]
		total_matches = []
		all_users = users.find({})
		all_riders = []
		for cur_rider in all_users:
			flag = 0
			form_personal_profile = cur_rider.get("form_personal_profile",False)
			form_rider_profile = cur_rider.get("form_rider_profile",False)
			form_medical_profile = cur_rider.get("form_medical_profile",False)
			form_bike_profile = cur_rider.get("form_bike_profile",False)
			form_race_profile = cur_rider.get("form_race_profile",False)
			"""if form_personal_profile == False or form_rider_profile == False or form_bike_profile == False or form_medical_profile == False or form_race_profile == False:
				flag = 1
			"""
			if flag == 0:
				all_riders.append(cur_rider)
		if rider[0] == "#":
			total_matches = []
			rider = rider[1:]
			for i in all_riders:
				un_id = str(i.get("_id"))
				un_id = un_id[:len(rider)]
				if un_id == rider:
					total_matches.append(i)
		else:
			counter = 0
			rider = rider.lower()
			for cur_rider in all_riders:
				cur_matches = []
				rider_len = len(rider)
				try:  
					cur_first_name = cur_rider["Name"]["first_name"]  
					cur_first_name = cur_first_name[:rider_len]
					if cur_first_name.lower() == rider:
						cur_matches.append(cur_rider)
				except:
					pass
				if len(cur_matches) == 0:
					try:
						cur_alias = cur_rider["name_alias"]
						cur_alias = cur_alias[:rider_len]
						if cur_alias.lower() == rider:
							cur_matches.append(cur_rider)
					except:
						pass
					if len(cur_matches) == 0:
						try:
							cur_last_name = cur_rider["Name"]["last_name"]
							cur_last_name = cur_last_name[:rider_len]
							if cur_last_name.lower() == rider:
								cur_matches.append(cur_rider)
						except:
							pass
						if len(cur_matches) == 0:
							try:
								cur_middle_name = cur_rider["Name"]["middle_name"]
								cur_middle_name = cur_middle_name[:rider_len]
								if cur_middle_name.lower() == rider:
									cur_matches.append(cur_rider)
							except:
								pass
							if len(cur_matches) == 0:
								try:
									cur_email = cur_rider["Email"]
									cur_email = cur_email[:rider_len]
									if cur_email.lower() == rider:
										cur_matches.append(cur_rider)
								except:
									pass
								if len(cur_matches) == 0:
									try:
										cur_mobile = cur_rider["Mobile"]
										cur_mobile = cur_mobile[:rider_len+1]
										if cur_mobile.lower() == "+" + rider:
											cur_matches.append(cur_rider)
									except:
										pass
				if len(cur_matches) != 0:
					total_matches.append(cur_matches[0])
		if len(total_matches) != 0:
			final_matches.append(total_matches)
			for i in range(1, len(search_rider)):
				rider = search_rider[i]
				rider_len = len(rider)
				step_total_matches = [] 
				counter = 0
				for j in total_matches:
					cur_matches = []
					if rider[0] == "#":
						try:
							if j["_id"][:rider_len-1] == rider[1:]:
								cur_matches.append(j)
						except:
							pass
					else:
						rider = rider.lower()
						try:
							if j["Name"]["first_name"][:rider_len].lower() == rider:
								cur_matches.append(j)
						except:
							pass
						if len(cur_matches) == 0:
							try:
								if j["name_alias"][:rider_len].lower() == rider:
									cur_matches.append(j)
							except:
								pass
							if len(cur_matches) == 0:
								try:
									if j["Name"]["last_name"][:rider_len].lower() == rider:
										cur_matches.append(j)
								except:
									pass
								if len(cur_matches) == 0:
									try:
										if j["Name"]["middle_name"][:rider_len].lower() == rider:
											cur_matches.append(j)
									except:
										pass
									if len(cur_matches) == 0:
										try:
											if j["Email"][:rider_len].lower() == rider:
												cur_matches.append(j)
										except:
											pass
										if len(cur_matches) == 0:
											try:
												if j["Mobile"][:rider_len + 1].lower() == "+" + rider:
													cur_matches.append(j)
											except:
												pass
					counter += 1
					if cur_matches != []:
						step_total_matches.append(cur_matches[0])
				total_matches = step_total_matches[:]
		else:
			output = "No Rider Found"
		if len(total_matches) == 0:
			output = "No Rider Found"
		else:
			output = []
			for i in total_matches:
				
				dic = {}
				try:
					dic["first_name"] = i["Name"]["first_name"]
				except:
					dic["first_name"] = ""
				try:
					dic["last_name"] = i["Name"]["last_name"]
				except:
					dic["last_name"] = ""
				try:
					dic["name_alias"] = i["name_alias"]		
				except:
					dic["name_alias"] = ""
				get_image = i.get("image",None)
				if get_image != None:
					image_var = "static/img/profile_images/" + get_image + "?r=" + str(randint(1,10000000))
					var = image_var
					if "?" in var : 
						var = var.split("?")[0]
					var = ROOT_DIR + "/" + var
					(width, height) = get_size(var)
				else:
					image_var = i.get("profile_pic")
					# (width, height) = get_size(image_var)
					(width, height) = (0,100)
				
				dic["profile_pic"] = image_var
				try:
					dic["dream_bike"] = i["dream_bike"]
				except:
					dic["dream_bike"] = ""
				try:
					dic["riding_style"] = ','.join(i["riding_style"])
				except:
					dic["riding_style"] = ""
				try:
					dic["state"] = i["address"]["state"]
				except:
					dic["state"] = ""
				try:
					dic["country"] = i["address"]["country"]
				except:
					dic["country"] = ""
				output.append(dic)
	
	if output == []:
		output = "No Rider Found"

	return render_template(
		"ridersearch.html",
		logged_in = logged_in,
		output = output,
		width = width,
		height = height,
		)

@appli.route("/",methods=["GET","POST"])
def homepage():
	logged_in = False
	if "email" in session:
		logged_in = True
		return render_template(
			"index.html",
			logged_in = logged_in,
			facebook_name = session["facebook_name"],
			profile_pic = session["profile_pic"],
			email = session["email"],
			)
	return render_template(
		"index.html",
		logged_in = logged_in,
		)

# Developer rider search to get all the rider id 
@appli.route("/developer_rider_search",methods=["GET","POST"])
def developer_rider_search():
	key = request.args.get("key",None)
	un_id = request.args.get("id",None)
	users = db.users
	dev_search = db.developer_search
	if key == None or un_id == None:
		return redirect(url_for("views.homepage"))
	find_key = dev_search.find_one({"key.password":key})
	if find_key == None:
		return jsonify([{"Error":"No Such Key Found"}])
	try:
		find_id = users.find_one({"_id":ObjectId(un_id)})
	except:
		find_id = None
	if find_id == None:
		return jsonify([{"Error":"No Such Id Found"}])
	rider = {}
	for i in find_id:
		if i!="_id":
			rider[i] = find_id[i]
	return jsonify([rider])

# 404 for wrong url input
@app.errorhandler(404)
def page_not_found(e):
	logged_in = False
	if "email" in session:
		logged_in = True
	return render_template('404.html',logged_in=logged_in), 404