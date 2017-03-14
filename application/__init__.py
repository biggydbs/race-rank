from flask import Flask, render_template, send_from_directory, url_for, session, request, flash, g, redirect
from flask_oauth import OAuth
from flask import session
from decorators import login_required
from pymongo import MongoClient
import os

app = Flask(__name__)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configs
app.config.update(
    DEBUG = True,
    SECRET_KEY = "race_rankings",
    MAX_CONTENT_LENGTH = 1024 * 1024,
    UPLOAD_FOLDER = ROOT_DIR + "/static/img/profile_images/",
    UPLOAD_FOLDER_ID = ROOT_DIR + "/static/id_proof/",
    UPLOAD_FOLDER_ID_RIDER = ROOT_DIR + "/static/rider_id_proof/",
    UPLOAD_FOLDER_ID_RIDER_INSURANCE = ROOT_DIR + "/static/rider_insurance_certificate/",
    UPLOAD_CSV_TEMP = ROOT_DIR + "/static/csv_temp/",
    UPLOAD_CSV_FINAL = ROOT_DIR + "/static/csv_final/"
)

oauth = OAuth()

client = MongoClient('ds131340.mlab.com', 31340)
handle.authenticate("biggydbs","biggy30695")

db = client["race_ranking"]

# Register the blueprint (routes)
from application.views import appli
app.register_blueprint(appli)
from application.controllers import appli
app.register_blueprint(appli)
from application.admin import appli
app.register_blueprint(appli)