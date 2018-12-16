# Olivia Gardella
# SI364 Final
# API link: https://newsapi.org/docs/
# https://newsapi.org/docs/endpoints/top-headlines
# Referenced hw4 for user authentication, hw5 for updating, and midterm for api



###############################
####### SETUP (OVERALL) #######
###############################

# Import statements
import os
import requests
import json
from flask import Flask, render_template, session, redirect, url_for, flash, request
from flask_wtf import FlaskForm
from flask_script import Manager, Shell
from wtforms import StringField, SubmitField, FileField, PasswordField, BooleanField, SelectMultipleField, ValidationError
from wtforms.validators import Required, Length, Email, Regexp, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager, Shell
# for login management
from flask_login import LoginManager, login_required, logout_user, login_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# App setup code
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.debug = True

# App configurations
app = Flask(__name__)
app.debug = True
app.use_reloader = True
app.config['SECRET_KEY'] = 'hardtoguessstring'
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL') or "postgresql://postgres:si364@localhost/gardellaFinal"
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# App addition setups
manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
manager.add_command('db', MigrateCommand)

# Login configurations setup
login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)

# API key
API_KEY = '93576556daae407cb66107833a825ec3'






##################
##### MODELS #####
##################

# association table between headlines and collections (many:many relationship between headlines and collections)
headline_collection = db.Table('headline_collection', db.Column('news_id', db.Integer, db.ForeignKey('news.id')), db.Column('headlineCollection_id', db.Integer, db.ForeignKey('headlineCollection.id')))


# user model for users to log in
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(200), unique=True, index=True)
    email = db.Column(db.String(80), unique=True, index=True)
    password_hash = db.Column(db.String(140))

    # one:many relationship between users and collections (one user can have many collections)
    collections = db.relationship('HeadlineCollection', backref='User')

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)


# news model to store found article headlines
class News(db.Model):
    __tablename__ = "news"
    id = db.Column(db.Integer, primary_key=True)
    headline = db.Column(db.String(400))

    def __repr__(self):
        return "{} | ID:{}".format(self.headline, self.id)


# sources model to store sources user has logged
class Sources(db.Model):
    __tablename__ = "sources"
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(50))

    def __repr__(self):
        return "{} | ID:{}".format(self.source, self.id)


# collection model to store user's collections of found headlines
class HeadlineCollection(db.Model):
    __tablename__ = 'headlineCollection'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))

    # one:many relationship with the User model (one user can have many collections)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # many:many relationship with the News model (one headline can be in many collections, one collection can have many headlines)
    headlines = db.relationship('News', secondary = headline_collection, backref = db.backref('headlineCollection', lazy='dynamic'), lazy='dynamic')







###################
###### FORMS ######
###################

# form to register for a new account
class RegistrationForm(FlaskForm):
    email = StringField('Email:', validators=[Required(), Length(1,80), Email()])
    username = StringField('Username:', validators=[Required(), Length(1,80)])
    password = PasswordField('Password:', validators=[Required(), EqualTo('password2',message="Passwords must match")])
    password2 = PasswordField("Confirm Password:", validators=[Required()])
    submit = SubmitField('Register')

    def validate_email(self,field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self,field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already taken')


# form to log into account
class LoginForm(FlaskForm):
    email = StringField('Email:', validators=[Required(), Length(1,70), Email()])
    password = PasswordField('Password:', validators=[Required()])
    remember_me = BooleanField('Keep me logged in')
    submit = SubmitField('Log In')


# form to enter a word to find related headlines
class NewsForm(FlaskForm):
    keyword = StringField('Enter a keyword:', validators=[Required(), Length(1,80)])
    submit = SubmitField('Submit')

    # custom validator to make sure keyword does not have these special characters
    def validate_keyword(self,field):
        keyword = field.data
        special_chrs = ['@', '!', '.']
        for char in special_chrs:
            if char in keyword:
                raise ValidationError("Keyword should not contain the characters '@', '!', or '.'! Take these out and try again.")


# form to enter sources for news
class SourcesForm(FlaskForm):
    source = StringField("Enter one source where you get news from:", validators=[Required()])
    submit = SubmitField('Submit')


# form to select articles and create collection
class CreateCollectionForm(FlaskForm):
    name = StringField('Collection Name (only one word):', validators=[Required()])
    selected_articles = SelectMultipleField('Articles to include:')
    submit = SubmitField("Create Collection")

    # custom validator to make sure collection name is only one word
    def validate_name(self,field):
        name = field.data
        if ' ' in name:
            raise ValidationError("Collection name should only be one word - take out space and try again.")


# form to update saved headline in collection
class UpdateButtonForm(FlaskForm):
    update = SubmitField("Update")

# form to delete saved headline in collection
class DeleteButtonForm(FlaskForm):
    delete = SubmitField("Delete")

# form to update headline
class UpdateHeadlineForm(FlaskForm):
    update_article = StringField("What is the new headline?", validators=[Required()])
    update = SubmitField('Update')





######################################
############ HELPER FXNS #############
######################################

# get_headline_from_api to get the most recent headline based on keyword from the news api (use url, params, json)
def get_headline_from_api(keyword):
    baseurl = 'https://newsapi.org/v2/top-headlines?'
    params = {}
    params['apiKey'] = API_KEY
    params['q'] = keyword
    response = requests.get(baseurl, params=params)
    response_dict = json.loads(response.text)
    if len(response_dict['articles']) > 0:
        title = response_dict['articles'][0]['title']
        return title
    else:
        flash('There are no recent headlines pertaining to this keyword, try a different keyword!')
        return ''

# get_or_create_headline to query for the headline and then add to the database
def get_or_create_headline(keyword):
    key = get_headline_from_api(keyword)
    if len(key) > 0:
        headline = News(headline=key)
        db.session.add(headline)
        db.session.commit()
        return headline
    else:
        return 'none'

# get_or_create_collection to query for user's collection and add to database
def get_or_create_collection(name, current_user, headline_list=[]):
    headline_collection = HeadlineCollection.query.filter_by(name=name, user_id=current_user.id).first()
    if headline_collection:
        return headline_collection
    else:
        headline_collection = HeadlineCollection(name=name, user_id=current_user.id, headlines=[])
        for headline in headline_list:
            headline_collection.headlines.append(headline) #????
        db.session.add(headline_collection)
        db.session.commit()
        return headline_collection







#######################
###### VIEW FXNS ######
#######################

# load function
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# route for error handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404error.html'), 404

# route to home page, introduces app, links to other screens, asks users to log in or create an account
@app.route('/', methods=['GET', 'POST'])
def home():
    return render_template('base.html')

# route to log in to account
@app.route('/login', methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('home'))
        flash('Invalid username or password - try again!')
    return render_template('login.html', form=form)

# route to log out
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have now been logged out.')
    return redirect(url_for('home'))

# route to register for new account
@app.route('/register', methods=["GET","POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user_to_add = User(email=form.email.data, username=form.username.data, password=form.password.data)
        db.session.add(user_to_add)
        db.session.commit()
        flash('Account created! You can now log in.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

# route to enter keyword to get article headline
@app.route('/news', methods=['GET', 'POST'])
def news():
    form = NewsForm()
    num_news = len(News.query.all())
    if form.validate_on_submit():
        news = get_or_create_headline(form.keyword.data)
        if news == 'none':
            return render_template('news.html', form=form, num_news=num_news)
        return redirect(url_for('news_results'))
    return render_template('news.html', form=form, num_news=num_news)

# route to see all found headlines thus far
@app.route('/news_results')
def news_results():
    news = News.query.all()
    num_news = len(News.query.all())
    return render_template('news_results.html', news=news, num_news=num_news)

# route to enter news sources (only for logged in users)
@app.route('/sources', methods=['GET', 'POST'])
@login_required
def sources():
    form = SourcesForm()
    if form.validate_on_submit():
        source = form.source.data
        source_in_db = Sources.query.filter_by(source=source).first()
        if source_in_db:
            flash('This source has already been added to the list. Try another source!')
            return redirect(url_for('sources'))
        source = Sources(source=source)
        db.session.add(source)
        db.session.commit()
        flash('Source successfully saved!')
        return(redirect(url_for('sources')))
    sources = Sources.query.all()
    all_sources = []
    for s in sources:
        all_sources.append(s)
    return render_template('sources.html', form=form, all_sources=all_sources)

# route to create a new collection to store headlines (only for logged in users)
@app.route('/create_collection', methods=["GET","POST"])
@login_required
def create_collection():
    form = CreateCollectionForm()
    headlines = News.query.all()
    choices = [(str(h.id), h.headline) for h in headlines]
    form.selected_articles.choices = choices
    if form.validate_on_submit():
        headline_list = []
        for x in form.selected_articles.data:
            headline_list.append(News.query.filter_by(id=x).first())
        get_or_create_collection(form.name.data, current_user, headline_list)
        return redirect(url_for('collections'))
    return render_template('create_collection.html', form=form)

# route to view collections
@app.route('/collections', methods=["GET","POST"])
@login_required
def collections():
    form = DeleteButtonForm()
    collections = HeadlineCollection.query.filter_by(user_id=current_user.id).all()
    return render_template('collections.html', collections=collections, form=form)

# route to delete a collection
@app.route('/delete/<col>', methods=["GET","POST"])
@login_required
def delete(col):
    collection = HeadlineCollection.query.filter_by(name=col).first()
    db.session.delete(collection)
    flash("Deleted collection {}".format(col))
    return redirect(url_for('collections'))

# route to view each collection and the headlines inside it
@app.route('/collection/<id>', methods=["GET","POST"])
def view_collection(id):
    form = UpdateButtonForm()
    collection = HeadlineCollection.query.filter_by(id=int(id)).first()
    headlines = collection.headlines.all()
    return render_template('view_collection.html', collection=collection, headlines=headlines, form=form)

# route to update a headline
@app.route('/update/<headline>', methods=["GET","POST"])
def update(headline):
    form = UpdateHeadlineForm()
    if form.validate_on_submit():
        headlines = News.query.filter_by(headline = headline).first()
        headlines.headline = form.update_article.data
        db.session.commit()
        flash("Updated the article {}".format(headline))
        return redirect(url_for('collections'))
    return render_template("update_article.html", headline=headline, form=form)






## Code to run the application
if __name__ == '__main__':
    db.create_all()
    manager.run()
    app.run(use_reloader=True,debug=True)
