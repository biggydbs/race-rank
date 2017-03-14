from application import db, ROOT_DIR
import xlrd as xl
from PIL import Image
import re
import urllib, cStringIO
import bson
from datetime import date
from sync_ranks import advantage_points
import datetime
import time
import csv
from bson.objectid import ObjectId
import json
import pymongo
import operator

def check_admin(email):
	admins = db.admin
	allowed_emails = admins.find({})
	for i in allowed_emails:
		allowed_emails = i["Email"]
	try:
		check_mail = unicode(session["email"], "utf-8")
	except:
		check_mail = email
	if check_mail in allowed_emails:
		return True
	else:
		return False

# Update advantage points 
def update_advantage_points(race_name):
	results = db.results
	result = results.find_one(
			{	
				"race_name" : race_name
			}
		)
	adv_pts = advantage_points()
	cur_race_result = result["race_result"]
	race_time_dic = {}
	adv_pts_dic = {} 
	for cur_ser_num in cur_race_result:
		rider_tag = cur_race_result[cur_ser_num]["rider_tag"]
		total_race_time = cur_race_result[cur_ser_num]["total_race_time"]
		if rider_tag != "":
			try:
				race_time = float(total_race_time)
				race_time_dic[cur_ser_num] = total_race_time
			except:
				adv_pts_dic[cur_ser_num] = adv_pts["dnf"]
	# Sort riders according to the time
	race_time_dic = sorted(race_time_dic.items(), key=operator.itemgetter(1))
	ct = 1 
	# assign the advantage points for every registered rider
	for race_time in race_time_dic:
		if ct == 1:
			adv_pts_dic[race_time[0]] = adv_pts["first"]
		if ct == 2:
			adv_pts_dic[race_time[0]] = adv_pts["second"]
		if ct == 3:
			adv_pts_dic[race_time[0]] = adv_pts["third"]
		if ct > 3:
			adv_pts_dic[race_time[0]] = adv_pts["finisher"]
		ct += 1
	# update the advantage point 
	for cur_ser_num in cur_race_result:
		try:
			adv_point = adv_pts_dic[cur_ser_num]
			ser_num = "race_result.{cur_ser_num}.advantage_point".format(cur_ser_num=cur_ser_num)
			results.update_one(
					{
						"race_name" : race_name
					},
					{
						"$set":{
							str(ser_num) : float(adv_point)
						}
					}
				)
		except:
			pass
	return "Updated"

				
# Update CGPA ratings for the race_name	
def update_cgpa_ratings_with_name(race_name):
	users = db.users
	results = db.results
	result = results.find_one(
			{	
				"race_name" : race_name
			}
		)
	cur_race_result = result["race_result"]
	for cur_ser_num in cur_race_result:
		rider_tag = cur_race_result[cur_ser_num]["rider_tag"]
		final_score = cur_race_result[cur_ser_num]["final_score"]
		if rider_tag != "":
			# Calculate previous cgpa
			prev_cgpa = users.find_one(
					{
						"_id":ObjectId(rider_tag)
					},
					{ 
						"cgpa_rating" : 1
					}
				)
			# Update new CGPA
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

# CSV to document converter
def csv_to_json(file_path, db_race_difficulty, db_company_name, db_company_description, db_company_number, db_company_email, db_company_address_part_one, db_company_address_part_two, db_company_address_part_three, db_company_address_part_four, db_company_nation, db_race_date):
	results = db.results
	reader = csv.DictReader(open(file_path))
	all_data = []
	for i in reader:
		cur_data = {}
		day_counter = 0
		for j in i:
			row = j.replace(" ","_").lower()
			if "day" in row:
				day_counter += 1
				# time into seconds
				try:
					x = time.strptime(i[j],'%H:%M:%S')
					time_in_seconds = datetime.timedelta(hours=x.tm_hour,minutes=x.tm_min,seconds=x.tm_sec).total_seconds()
					cur_data[row] = time_in_seconds
				except:
					cur_data[row] = i[j]
			else:
				cur_data[row] = i[j]
		all_data.append(cur_data)
	ct = 1
	for i in all_data:
		i["rider_sheet_name"] = "r" + str(ct)
		i["advantage_point"] = 0
		i["rider_tag"] = ""
		ct += 1
		for j in range(1,day_counter+1):
			try:
				i["race_results"].append(i["day_" + str(j)])
			except:
				i["race_results"] = [i["day_" + str(j)]]
	users = db.users
	all_riders = users.find({})
	for i in all_riders:
		for j in all_data:
			if j["rider_tag"] == "":
				try:
					name = ""
					prefix = i["Name"]["prefix"]
					first_name = i["Name"]["first_name"]
					middle_name = i["Name"]["middle_name"]
					last_name = i["Name"]["last_name"]
					if prefix != "":
						name += prefix + " "
					if first_name != "":
						name += first_name + " "
					if middle_name != "":
						name += middle_name + " "
					if last_name != "":
						name += last_name + " "
					name = name.strip().lower()	
					try:
						name = name.encode('utf-8')
					except:
						pass
					if name == j["name"].lower():
						j["rider_tag"] = str(i["_id"])
						break
				except:
					j["rider_tag"] = ""
	final_results = {}
	final_results["race_result"] = {}
	ct = 1
	#  assign all above calculated data
	for i in all_data:
		cur_race_result = {}
		serial_num = "s" + str(ct)
		cur_race_result[serial_num] = {}
		cur_race_result[serial_num]["advantage_point"] = i["advantage_point"]
		cur_race_result[serial_num]["category"] = i["category"]
		cur_race_result[serial_num]["rider_tag"] = str(i["rider_tag"])
		cur_race_result[serial_num]["race_results"] = i["race_results"]
		cur_race_result[serial_num]["rider_sheet_name"] = i["rider_sheet_name"]
		cur_race_result[serial_num]["name"] = i["name"]
		cur_race_result[serial_num]["final_score"] = 0.0
		try:
			cur_race_result[serial_num]["total_race_time"] = sum(map(int,cur_race_result[serial_num]["race_results"]))
		except:
			cur_race_result[serial_num]["total_race_time"] = "DNF"
		final_results["race_result"]["s" + str(ct)] = cur_race_result["s" + str(ct)]
		ct += 1
	final_results["difficulty"] = db_race_difficulty
	final_results["type"] = "professional"
	final_results["active"] = "yes"
	final_results["nationality"] = db_company_nation
	final_results["contact"] = {
		"mobile" : db_company_number,
		"email" : db_company_email,
		"address" : {
			    "address_1": db_company_address_part_one,
			    "address_2": db_company_address_part_two,
			    "state": db_company_address_part_three, 
			    "country": db_company_address_part_four
		    }
		}
	try:
		db_race_date = db_race_date.encode('utf-8')
	except:
		pass
	if "." in db_race_date:
		db_race_date = db_race_date.split(".")
	elif "-" in db_race_date:
		db_race_date = db_race_date.split("-")
	else:
		db_race_date = db_race_date.split("/")
	final_results["race_date"] = {
		"date" : db_race_date[2],
		"month" : db_race_date[1],
		"year" : db_race_date[0],
		}
	final_results["description"] = db_company_description
	final_results["race_name"] = file_path.split("/")[-1].split(".")[0]
	results.insert_one(final_results)
	return "SUCCESS"

def calculate_age(born):
	today = date.today()
	return today.year - int(born["year"]) - ((today.month, today.day) < (int(born["month"]), int(born["date"])))

# Update Users database
def read_xlsx():
	path = ROOT_DIR + "/central_db.xlsx"
	workbook = xl.open_workbook(path)
	worksheet = workbook.sheet_by_index(0)
	offset = 0
	rows = []
	fields = []
	for i,row in enumerate(range(worksheet.nrows)):	
		r = []
		for j,col in enumerate(range(worksheet.ncols)):
			if i != offset:
				value = worksheet.cell_value(i,j)
				if value == "" or value == "nothing" or value == "none" or value == "N-A" or value == "None" or value == "not known" or value == "NIL" or value == "Nil" or value == "nil" or value == "NA" or value == "n-a" or value == "na" or value == "N-a" or value == "nothing":
					value = ""
				if j == 10 or j == 11 or  j == 16:
					try:
						r.append(int(value))
					except:
						r.append(value)
				else:

					r.append(value)
			else:
				r.append(worksheet.cell_value(i,j))
		if i != offset:
			rows.append(r)
		else:
			fields = r[:]
			fields[6] = "address1".decode('utf-8') 
			fields[7] = "address2".decode('utf-8') 
			fields[8] = "state".decode('utf-8') 
			fields[9] = "country".decode('utf-8') 
			fields[14] = "relation_name".decode('utf-8') 
			fields[15] = "relation".decode('utf-8') 
			fields[16] = "relation_contact_number".decode('utf-8') 
	store_all_predefined_users(rows, fields)

# Store all users
def store_all_predefined_users(rows, fields):

	final_data = []
	for row in rows:
		count = 0
		dic = {}
		address = {}
		emergency_contact = {}
		for each_row in row:
			if count == 0:
				temp = {
					"prefix" : "",
					"first_name" : "",
					"middle_name" : "",
					"last_name" : ""
				}
				each_row = each_row.encode('utf-8')
				if each_row != "":
					each_row = each_row.split()
					len_row = len(each_row)
					temp["first_name"] = each_row[0]
					if len_row == 2:
						temp["last_name"] = each_row[1]
					if len_row == 3:
						temp["middle_name"] = each_row[1]
						temp["last_name"] = each_row[2]
				
				dic[fields[count]] = temp
			elif count == 2:
				try:
					each_row = each_row.encode('utf-8')
				except:
					pass
				if "." in each_row:
					each_row = each_row.split(".")
				elif "-" in each_row:
					each_row = each_row.split("-")
				else:
					each_row = each_row.split("/")
				temp = {
					"date" : int(each_row[0]),
					"month" : int(each_row[1]),
					"year" : int(each_row[2])
				}
				dic[fields[count]] = temp
			elif count == 6 or count == 7 or count == 8:
				address[fields[count]] = each_row
			elif count == 9:
				address[fields[count]] = each_row
				dic["address"] = address
			elif count == 14 or count == 15:
				emergency_contact[fields[count]] = each_row
			elif count == 16:
				emergency_contact[fields[count]] = each_row
				dic["emergency_contact"] = emergency_contact
			else:
				dic[fields[count]] = each_row
			count += 1
		dic["elo_rating"] = 1000
		dic["cgpa_rating"] = 0
		final_data.append(dic)

	users = db.users
	for user in final_data:
		users.insert_one(user)

# get the size of an image
def get_size(get_image):
	if get_image == "":
		return (0,0)
	if "http" in get_image:
		file = cStringIO.StringIO(urllib.urlopen(get_image).read())
		get_image = file
	with Image.open(get_image) as im:
		width, height = im.size
		if height/width > 2:
			height = 200
		elif height/width < 0.7:
			height = 70
		else:
			height = ( height/width ) * 100
		return (width,height)

# Time Validation
def validate_time(race_time):
	try:
		check = race_time.split(":")
		if len(check) == 3:
			for i in check:
				try:
					x = int(i)
				except:
					return False
			return True
		else:
			return False
	except:
		return False

# validation of name
def validate_name(name):
	match1 = re.match(r'(.*?)\s\s', name)
	match2 = re.search(r'^[A-z][A-z|\s]+$', name)
	if match2 : 
		if match1:
			return False
		else:
			return True
	else:
		return False

# validate the name with prefix
def validate_name_prefix(name):
	match1 = re.match(r'(.*?)\s\s', name)
	match2 = re.search(r'^[A-z][A-z|\.|\s]+$', name)
	if match2 :
		if match1:
			return False
		else:
			return True
	else:
		return False

# for reducing overhead html is created
def print_html(profile_pic, facebook_name, height, email):
	if email == "":
		return """
		<!-- START PAGE SIDEBAR -->
            <div class="page-sidebar">
                <!-- START X-NAVIGATION -->
                <ul class="x-navigation">
                    <li class="xn-logo">
                        <a href="#">User</a>
                        <a href="#" class="x-navigation-control"></a>
                    </li>
                        <li class="xn-title">Personal</li>
                    <li>
                        <a href="/login"><span class="fa fa-desktop"></span> <span class="xn-text">Login</span></a>
                    </li> 
                    <li >
                        <a href="/rider_search"><span class="fa fa-desktop"></span> <span class="xn-text">Rider Search</span></a>   
                    </li>
                    <li >
                        <a href="/rankings"><span class="fa fa-desktop"></span> <span class="xn-text">View Ranks</span></a>   
                    </li>
                    
                </ul>
                <!-- END X-NAVIGATION -->
            </div>
            <!-- END PAGE SIDEBAR -->
		""".format(profile_pic=profile_pic,facebook_name=facebook_name,height=height,email=email)
	else:
		return """
		<!-- START PAGE SIDEBAR -->
            <div class="page-sidebar">
                <!-- START X-NAVIGATION -->
                <ul class="x-navigation">
                    <li class="xn-logo">
                        <a href="#">User</a>
                        <a href="#" class="x-navigation-control"></a>
                    </li>
                    <li class="xn-profile">
                        <a href="#" class="profile-mini">
                            <img src="{profile_pic}"  alt="{facebook_name}"/>
                        </a>
                        <div class="profile">
                            <div class="profile-image">
                                <img src="{profile_pic}" height="{height}px" alt="{facebook_name}"/>
                            </div>
                            <div class="profile-data">
                                <div class="profile-data-name">{facebook_name}</div>
                                <div class="profile-data-title">{email}</div>
                            </div>
                            
                        </div>                                                                        
                    </li>
                        <li class="xn-title">Personal</li>
                        <li>
                            <a href="/admin_login"><span class="fa fa-desktop"></span> <span class="xn-text">Admin Portal</span></a> 
                    	</li>
                    <li class="active">
                        <a href="/userhome"><span class="fa fa-desktop"></span> <span class="xn-text">Dashboard</span></a>
                    </li> 
                    <li>

                        <a href="/rider_search"><span class="fa fa-desktop"></span> <span class="xn-text">Rider Search</span></a>   
                    </li >
                    <li>
                        <a href="/rankings"><span class="fa fa-desktop"></span> <span class="xn-text">View Ranks</span></a>   
                    </li>
                    <li class="xn-title">Updates</li>
                  
                    <li class="xn-openable">
                        <a href="#"><span class="fa fa-pencil"></span> <span class="xn-text">Profile Updates</span></a>
                        <ul>
                            <li><a href="/form_personal_profile"><span class="fa fa-file-text-o"></span> Personal Profile</a></li>
                            <li><a href="/form_rider_profile"><span class="fa fa-list-alt"></span> Rider Profile</a></li>
                            <li><a href="/form_bike_profile"><span class="fa fa-arrow-right"></span> Bike Profile</a></li>
                            <li><a href="/form_medical_profile"><span class="fa fa-text-width"></span> Medical Profile</a></li>
                        </ul>
                    </li>
                  
                    <li class="xn-openable">
                        <a href="#"><span class="fa fa-pencil"></span> <span class="xn-text">Race Updates</span></a>
                        <ul>
                            <li><a href="/form_race_profile"><span class="fa fa-list-alt"></span> Race Profile</a></li>
                        </ul>
                    </li>
                
                    
                </ul>
                <!-- END X-NAVIGATION -->
            </div>
            <!-- END PAGE SIDEBAR -->
		""".format(profile_pic=profile_pic,facebook_name=facebook_name,height=height,email=email)